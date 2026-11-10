"""Segurança HTTP, e-mails transacionais, nova senha, LGPD, devoluções e lembrete de sacola."""
import logging
import unittest
from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import select

import test_admin as admin
import test_checkout as checkout
from app.core.config import get_settings
from app.maintenance import run_batch
from app.models.account import PasswordReset
from app.models.address import Address
from app.models.cart import Cart
from app.models.notification import Notification
from app.models.order import Order
from app.models.payment import utc_now
from app.models.product import Product
from app.models.user import User
from app.services.email_provider import MemoryProvider
from app.services.legal_service import TERMS_VERSION

PASSWORD = "Minha frase segura 123!"


class Base(unittest.TestCase):
    tearDown = checkout.CheckoutTests.tearDown
    order = checkout.CheckoutTests.order
    post = checkout.CheckoutTests.post
    webhook = checkout.CheckoutTests.webhook

    def setUp(self):
        admin.AdminTests.setUp(self)
        MemoryProvider.outbox.clear()
        MemoryProvider.fail_next = 0

    def register(self, email="ana@example.com", marketing=False, headers=None):
        response = self.client.post("/api/v1/auth/register", headers=self.headers if headers is None else headers,
                                    json={"email": email, "password": PASSWORD, "accept_terms": True,
                                          "marketing_opt_in": marketing})
        self.assertEqual(response.status_code, 201, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def login(self, password=PASSWORD, email="ana@example.com"):
        return self.client.post("/api/v1/auth/login", json={"email": email, "password": password})

    def paid_order(self, auth, key="paid-key-1"):
        order = self.client.post("/api/v1/orders", headers={**auth, "Idempotency-Key": key}, json=self.body).json()
        charge = self.client.post(f"/api/v1/orders/{order['id']}/pix", headers=auth).json()
        self.assertEqual(self.webhook(charge).status_code, 200)
        return order

    def advance(self, order_id, status, tracking=None):
        return self.client.post(f"/api/v1/admin/orders/{order_id}/fulfillment", headers=self.admin_headers,
                                json={"status": status, **({"tracking_code": tracking} if tracking else {})})

    def queued(self, kind=None):
        with self.sessions() as db:
            statement = select(Notification).order_by(Notification.id)
            if kind:
                statement = statement.where(Notification.kind == kind)
            return list(db.scalars(statement))

    def dispatch(self):
        return run_batch(self.sessions)


class SecurityHeaderTests(Base):
    def test_security_headers_on_every_response(self):
        response = self.client.get("/api/v1/products")
        for name, value in [("x-content-type-options", "nosniff"), ("x-frame-options", "DENY"),
                            ("referrer-policy", "no-referrer")]:
            self.assertEqual(response.headers[name], value)
        self.assertIn("default-src 'none'", response.headers["content-security-policy"])
        self.assertNotIn("cache-control", response.headers)  # vitrine pública pode ir para cache
        self.assertEqual(self.client.get("/api/v1/cart", headers=self.headers).headers["cache-control"], "no-store")
        self.assertNotIn("strict-transport-security", response.headers)  # http local
        self.assertNotIn("content-security-policy", self.client.get("/docs").headers)  # Swagger carrega scripts

    def test_hsts_over_https(self):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app, base_url="https://testserver") as client:
            self.assertIn("max-age=31536000", client.get("/health").headers["strict-transport-security"])

    def test_security_log_never_contains_password_or_email(self):
        self.register()
        with self.assertLogs("lumen.security", level="INFO") as logs:
            self.assertEqual(self.login(password="senha-errada-bem-longa").status_code, 401)
            self.assertEqual(self.login().status_code, 200)
        text = "\n".join(logs.output)
        self.assertIn("auth.login_failed", text)
        self.assertIn("auth.login", text)
        self.assertNotIn("senha-errada-bem-longa", text)
        self.assertNotIn("ana@example.com", text)


class ConsentAndLegalTests(Base):
    def test_registration_requires_terms_and_marketing_starts_off(self):
        body = {"email": "nova@example.com", "password": PASSWORD}
        self.assertEqual(self.client.post("/api/v1/auth/register", json=body).status_code, 422)
        self.assertEqual(self.client.post("/api/v1/auth/register", json={**body, "accept_terms": False}).status_code, 422)
        auth = self.register("nova@example.com")
        me = self.client.get("/api/v1/auth/me", headers=auth).json()
        self.assertEqual((me["marketing_opt_in"], me["terms_version"], me["terms_current"]), (False, TERMS_VERSION, True))
        on = self.client.put("/api/v1/users/me/consents", headers=auth, json={"marketing_opt_in": True}).json()
        self.assertTrue(on["marketing_opt_in"])
        with self.sessions() as db:
            user = db.scalar(select(User).where(User.email == "nova@example.com"))
            self.assertIsNotNone(user.terms_accepted_at)
            user.terms_version = "2020-01"  # termos mudaram depois do aceite
            db.commit()
        self.assertFalse(self.client.get("/api/v1/auth/me", headers=auth).json()["terms_current"])
        renewed = self.client.put("/api/v1/users/me/consents", headers=auth,
                                  json={"marketing_opt_in": False, "accept_terms": True}).json()
        self.assertEqual((renewed["terms_current"], renewed["marketing_opt_in"]), (True, False))

    def test_legal_documents(self):
        listed = self.client.get("/api/v1/legal").json()
        self.assertEqual([d["slug"] for d in listed], ["privacy", "terms", "returns"])
        privacy = self.client.get("/api/v1/legal/privacy").json()
        self.assertIn("LGPD", privacy["content"])
        self.assertIn("a informar antes do início das vendas", privacy["content"])
        with patch.object(get_settings(), "STORE_DOCUMENT", "12.345.678/0001-90"), \
                patch.object(get_settings(), "STORE_CONTACT_EMAIL", "atendimento@example.com"):
            terms = self.client.get("/api/v1/legal/terms").json()["content"]
            self.assertIn("12.345.678/0001-90", terms)
            self.assertIn("atendimento@example.com", self.client.get("/api/v1/legal/returns").json()["content"])
        self.assertIn("7 dias", self.client.get("/api/v1/legal/returns").json()["content"])
        self.assertEqual(self.client.get("/api/v1/legal/outro").status_code, 404)


class PasswordResetTests(Base):
    def request(self, email):
        return self.client.post("/api/v1/auth/password-reset", json={"email": email})

    def confirm(self, token, password="Outra frase segura 456!"):
        return self.client.post("/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": password})

    def test_reset_flow_is_single_use_and_revokes_sessions(self):
        old_session = self.register()
        unknown = self.request("ninguem@example.com")
        known = self.request("ANA@example.com ")
        self.assertEqual((unknown.status_code, known.status_code), (202, 202))
        self.assertEqual(unknown.json(), known.json())  # não revela quem tem conta
        self.assertEqual(len(MemoryProvider.outbox), 1)
        email = MemoryProvider.outbox[0]
        self.assertEqual(email.to, "ana@example.com")
        token = email.text.split("Seu código: ")[1].split()[0]
        with self.sessions() as db:
            stored = db.scalar(select(PasswordReset))
            self.assertNotEqual(stored.token_hash, token)  # só o hash fica no banco
            self.assertFalse(any(token in (n.body_text or "") for n in db.scalars(select(Notification))))
        self.assertEqual(self.confirm(token).status_code, 204)
        self.assertEqual(self.confirm(token).status_code, 422)  # uso único
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=old_session).status_code, 401)
        self.assertEqual(self.login().status_code, 401)
        self.assertEqual(self.login("Outra frase segura 456!").status_code, 200)
        self.assertEqual([n.kind for n in self.queued()], ["password_changed"])

    def test_expired_or_replaced_tokens_fail(self):
        self.register()
        self.request("ana@example.com")
        first = MemoryProvider.outbox[-1].text.split("Seu código: ")[1].split()[0]
        self.request("ana@example.com")
        second = MemoryProvider.outbox[-1].text.split("Seu código: ")[1].split()[0]
        self.assertEqual(self.confirm(first).status_code, 422)  # o pedido novo invalidou o antigo
        with self.sessions() as db:
            db.scalar(select(PasswordReset)).expires_at = utc_now() - timedelta(minutes=1)
            db.commit()
        self.assertEqual(self.confirm(second).status_code, 422)
        self.assertEqual(self.confirm("x" * 30, "curta").status_code, 422)

    def test_reset_link_when_app_url_is_configured(self):
        self.register()
        with patch.object(get_settings(), "PASSWORD_RESET_URL", "https://app.example.com/nova-senha?t={token}"):
            self.request("ana@example.com")
        self.assertIn("https://app.example.com/nova-senha?t=", MemoryProvider.outbox[-1].text)
        self.assertIn('href="https://app.example.com/nova-senha?t=', MemoryProvider.outbox[-1].html)

    def test_reset_is_rate_limited_per_email(self):
        for _ in range(5):
            self.assertEqual(self.request("ana@example.com").status_code, 202)
        self.assertEqual(self.request("ana@example.com").status_code, 429)


class OrderEmailTests(Base):
    def test_order_emails_once_each_and_body_erased_after_sending(self):
        auth = self.register()
        order = self.paid_order(auth)
        charge = self.client.get(f"/api/v1/orders/{order['id']}", headers=auth).json()
        self.webhook(charge, event_id="event-duplicado")  # aviso repetido do provedor
        self.assertEqual([n.kind for n in self.queued()], ["order_paid"])
        self.advance(order["id"], "shipped", "BR123456789BR")
        self.advance(order["id"], "delivered")
        self.assertEqual(self.dispatch()["emails_sent"], 3)
        subjects = [m.subject for m in MemoryProvider.outbox]
        ref = order["id"].split("-")[0].upper()
        self.assertEqual(subjects, [f"Pedido {ref} confirmado", f"Pedido {ref} a caminho", f"Pedido {ref} entregue"])
        paid = MemoryProvider.outbox[0]
        self.assertIn("Olá, Cliente.", paid.text)
        self.assertIn("R$ 94,80", paid.text)
        self.assertNotIn("52998224725", paid.text + paid.html)  # CPF nunca vai no e-mail
        self.assertIn("BR123456789BR", MemoryProvider.outbox[1].text)
        self.assertIn("7 dias", MemoryProvider.outbox[2].text)
        self.assertTrue(all(n.status == "sent" and n.body_html is None for n in self.queued()))

    def test_failed_delivery_is_retried_with_backoff(self):
        auth = self.register()
        self.paid_order(auth)
        MemoryProvider.fail_next = 1
        self.assertEqual(self.dispatch()["emails_retry"], 1)
        item = self.queued("order_paid")[0]
        self.assertEqual((item.status, item.attempts), ("pending", 1))
        self.assertEqual(self.dispatch()["emails_sent"], 0)  # ainda no intervalo de espera
        with self.sessions() as db:
            db.get(Notification, item.id).next_attempt_at = utc_now() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.dispatch()["emails_sent"], 1)
        self.assertEqual(len(MemoryProvider.outbox), 1)

    def test_customer_name_is_escaped_in_html(self):
        self.body["address"]["recipient"] = "<b>Ana</b> Lima"
        auth = self.register()
        self.paid_order(auth)
        self.dispatch()
        self.assertNotIn("<b>Ana</b>", MemoryProvider.outbox[0].html)
        self.assertIn("&lt;b&gt;Ana&lt;/b&gt;", MemoryProvider.outbox[0].html)


class ReturnTests(Base):
    def delivered(self, auth, days_ago=0):
        order = self.paid_order(auth)
        self.advance(order["id"], "shipped", "BR1")
        self.advance(order["id"], "delivered")
        if days_ago:
            with self.sessions() as db:
                db.get(Order, order["id"]).delivered_at = utc_now() - timedelta(days=days_ago)
                db.commit()
        return order

    def ask(self, auth, order_id, reason="arrependimento"):
        return self.client.post(f"/api/v1/orders/{order_id}/return", headers=auth,
                                json={"reason": reason, "details": "Não ficou como eu imaginava"})

    def decide(self, return_id, action, note="", restock=False):
        return self.client.post(f"/api/v1/admin/returns/{return_id}", headers=self.admin_headers,
                                json={"action": action, "note": note, "restock": restock})

    def stock(self):
        with self.sessions() as db:
            return db.get(Product, 1).stock

    def test_withdrawal_within_7_days_approved_and_refunded_with_restock(self):
        auth = self.register()
        order = self.paid_order(auth)
        self.assertEqual(self.ask(auth, order["id"]).status_code, 409)  # ainda não entregue
        self.advance(order["id"], "shipped", "BR1")
        self.advance(order["id"], "delivered")
        status = self.client.get(f"/api/v1/orders/{order['id']}/return", headers=auth).json()
        self.assertEqual((status["eligible"], sorted(status["reasons"]), status["request"]),
                         (True, ["arrependimento", "defeito"], None))
        created = self.ask(auth, order["id"])
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(self.ask(auth, order["id"]).status_code, 409)
        other = self.register("outra@example.com", headers={})
        self.assertEqual(self.client.get(f"/api/v1/orders/{order['id']}/return",
                                         headers=other).status_code, 404)  # pedido de outra pessoa
        return_id = created.json()["id"]
        self.assertEqual(self.decide(return_id, "refund").status_code, 409)  # precisa aprovar antes
        self.assertEqual(self.client.post(f"/api/v1/admin/returns/{return_id}", headers=self.customer_headers,
                                          json={"action": "approve"}).status_code, 403)
        self.assertEqual(self.decide(return_id, "approve").json()["status"], "approved")
        before = self.stock()
        refunded = self.decide(return_id, "refund", restock=True).json()
        self.assertEqual((refunded["status"], refunded["restocked"]), ("refunded", True))
        self.assertEqual(self.stock(), before + 2)
        self.assertEqual(self.client.get(f"/api/v1/orders/{order['id']}", headers=auth).json()["status"], "refunded")
        self.assertEqual([n.kind for n in self.queued() if n.kind.startswith("return")],
                         ["return_requested", "return_approved", "return_refunded"])
        listed = self.client.get("/api/v1/admin/returns?status=refunded", headers=self.admin_headers).json()
        self.assertEqual([r["id"] for r in listed], [return_id])

    def test_deadlines_and_rejection_needs_reason(self):
        auth = self.register()
        order = self.delivered(auth, days_ago=8)
        late = self.ask(auth, order["id"])
        self.assertEqual(late.status_code, 422)
        self.assertIn("7 dias", late.json()["detail"])
        created = self.ask(auth, order["id"], "defeito")  # defeito: até 90 dias
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.decide(created.json()["id"], "reject").status_code, 422)
        rejected = self.decide(created.json()["id"], "reject", note="A peça voltou com sinais de uso.")
        self.assertEqual(rejected.json()["status"], "rejected")
        self.dispatch()
        self.assertIn("A peça voltou com sinais de uso.", MemoryProvider.outbox[-1].text)


class DataRightsTests(Base):
    def test_export_requires_password_and_contains_everything(self):
        auth = self.register()
        self.client.post("/api/v1/users/me/addresses", headers=auth, json={
            "recipient": "Ana Lima", "postal_code": "59000000", "street": "Rua das Flores", "number": "10",
            "district": "Centro", "city": "Natal", "state": "RN"})
        self.client.post("/api/v1/favorites/1", headers=auth)
        self.paid_order(auth)
        self.assertEqual(self.client.post("/api/v1/users/me/data-export", headers=auth,
                                          json={"password": "errada"}).status_code, 401)
        data = self.client.post("/api/v1/users/me/data-export", headers=auth, json={"password": PASSWORD})
        self.assertEqual(data.status_code, 200)
        body = data.json()
        self.assertEqual(body["account"]["email"], "ana@example.com")
        self.assertEqual(body["addresses"][0]["city"], "Natal")
        self.assertEqual(len(body["orders"]), 1)
        self.assertEqual(body["orders"][0]["payer_document"], "52998224725")
        self.assertEqual(body["emails"][0]["kind"], "order_paid")
        self.assertEqual(data.headers["cache-control"], "no-store")

    def test_delete_account_anonymizes_and_keeps_orders(self):
        auth = self.register()
        self.client.post("/api/v1/users/me/addresses", headers=auth, json={
            "recipient": "Ana Lima", "postal_code": "59000000", "street": "Rua das Flores", "number": "10",
            "district": "Centro", "city": "Natal", "state": "RN"})
        pending = self.client.post("/api/v1/orders", headers={**auth, "Idempotency-Key": "pending-key"}, json=self.body)
        self.assertEqual(self.client.post("/api/v1/users/me/delete", headers=auth,
                                          json={"password": PASSWORD}).status_code, 409)
        self.client.post(f"/api/v1/orders/{pending.json()['id']}/cancel", headers=auth)
        self.assertEqual(self.client.post("/api/v1/users/me/delete", headers=auth,
                                          json={"password": "errada"}).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/users/me/delete", headers=auth,
                                          json={"password": PASSWORD}).status_code, 204)
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=auth).status_code, 401)
        self.assertEqual(self.login().status_code, 401)
        with self.sessions() as db:
            user = db.scalar(select(User).where(User.deleted_at.is_not(None)))
            self.assertTrue(user.email.endswith("@anonimizado.invalid"))
            self.assertIsNone(user.full_name)
            self.assertEqual(db.scalars(select(Address)).all(), [])
            self.assertEqual(len(db.scalars(select(Order)).all()), 1)  # pedido fica pelo prazo legal
        self.register()  # o e-mail fica livre para uma conta nova

    def test_admin_account_cannot_self_delete(self):
        with patch("app.services.privacy_service.verify_password", return_value=True):
            response = self.client.post("/api/v1/users/me/delete", headers=self.admin_headers,
                                        json={"password": "qualquer"})
        self.assertEqual(response.status_code, 409)


class CartReminderTests(Base):
    def age_cart(self, hours=25):
        with self.sessions() as db:
            for cart in db.scalars(select(Cart)):
                cart.updated_at = utc_now() - timedelta(hours=hours)
            db.commit()

    def test_one_reminder_only_with_consent_and_no_discount(self):
        self.register(marketing=False)
        self.age_cart()
        self.dispatch()
        self.assertEqual(self.queued("cart_reminder"), [])
        auth = self.client.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": PASSWORD}).json()
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        self.client.put("/api/v1/users/me/consents", headers=headers, json={"marketing_opt_in": True})
        with self.sessions() as db:
            for cart in db.scalars(select(Cart)):
                cart.reminded_at = None
            db.commit()
        with patch.object(get_settings(), "API_PUBLIC_URL", "https://api.example.com"):
            self.dispatch()
        reminders = [m for m in MemoryProvider.outbox if m.subject == "Sua seleção continua à sua espera"]
        self.assertEqual(len(reminders), 1)
        self.assertIn("Vestido × 2", reminders[0].text)
        self.assertNotIn("cupom", reminders[0].text.lower())
        self.assertIn("List-Unsubscribe", reminders[0].headers)
        self.dispatch()
        self.assertEqual(len(self.queued("cart_reminder")), 1)  # não repete sem mudança na sacola

        link = reminders[0].headers["List-Unsubscribe"].strip("<>")
        token = link.split("token=")[1]
        page = self.client.get(f"/api/v1/unsubscribe?token={token}")
        self.assertEqual(page.status_code, 200)
        self.assertIn("<form method=\"post\">", page.text)
        self.assertTrue(self.client.get("/api/v1/auth/me", headers=headers).json()["marketing_opt_in"])  # GET não muda nada
        done = self.client.post("/api/v1/unsubscribe", content=f"token={token}",
                                headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertIn("Pronto", done.text)
        self.assertFalse(self.client.get("/api/v1/auth/me", headers=headers).json()["marketing_opt_in"])
        again = self.client.post("/api/v1/unsubscribe", content=f"token={token}",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertIn("já foi usado", again.text)

    def test_guest_carts_and_recent_changes_get_nothing(self):
        self.register(marketing=True)
        self.dispatch()  # sacola mudou agora há pouco
        self.age_cart(hours=24 * 8)  # parada há mais de 7 dias
        self.dispatch()
        self.assertEqual(self.queued("cart_reminder"), [])


class ProductSheetTests(Base):
    def test_composition_and_care_in_admin_and_storefront(self):
        body = {**self.product_body, "composition": "100% linho", "care": "Lavar à mão"}
        created = self.client.post("/api/v1/admin/products", headers=self.admin_headers, json=body).json()
        public = self.client.get(f"/api/v1/products/{created['id']}").json()
        self.assertEqual((public["composition"], public["care"]), ("100% linho", "Lavar à mão"))
        too_long = {**body, "care": "x" * 301}
        self.assertEqual(self.client.post("/api/v1/admin/products", headers=self.admin_headers,
                                          json=too_long).status_code, 422)


if __name__ == "__main__":
    logging.disable(logging.NOTSET)
    unittest.main()
