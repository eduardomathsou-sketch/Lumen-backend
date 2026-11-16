"""Código de acesso (sessão): aparelhos conectados, sessão curta do admin e limites."""
import unittest
from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import func, select

import test_admin as admin
import test_checkout as checkout
from app.core.config import get_settings
from app.models.account import AccountSession
from app.models.payment import as_utc, utc_now
from app.models.user import User
from app.services.auth_service import device_label, digest

PASSWORD = "Minha frase segura 123!"
CHROME_WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
SAFARI_IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X) AppleWebKit/605.1.15 Version/19.0 Mobile/15E148 Safari/604.1"


class SessionTests(unittest.TestCase):
    tearDown = checkout.CheckoutTests.tearDown

    def setUp(self):
        admin.AdminTests.setUp(self)

    def register(self, email="ana@example.com"):
        response = self.client.post("/api/v1/auth/register", headers={"User-Agent": CHROME_WINDOWS},
                                    json={"email": email, "password": PASSWORD, "accept_terms": True})
        self.assertEqual(response.status_code, 201, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def login(self, email="ana@example.com", agent=SAFARI_IPHONE):
        response = self.client.post("/api/v1/auth/login", headers={"User-Agent": agent},
                                    json={"email": email, "password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_device_labels(self):
        self.assertEqual(device_label(CHROME_WINDOWS), "Chrome · Windows")
        self.assertEqual(device_label(SAFARI_IPHONE), "Safari · iPhone")
        self.assertEqual(device_label("Dart/3.13 (dart:io)"), "Aplicativo Lumen")
        self.assertEqual(device_label(None), "Aparelho não identificado")
        self.assertLessEqual(len(device_label("x" * 5000)), 60)

    def test_list_devices_and_revoke_one(self):
        desktop = self.register()
        phone = self.login()
        listed = self.client.get("/api/v1/auth/sessions", headers=desktop)
        self.assertEqual(listed.status_code, 200)
        devices = listed.json()
        self.assertEqual(sorted(d["device"] for d in devices), ["Chrome · Windows", "Safari · iPhone"])
        self.assertEqual([d["device"] for d in devices if d["current"]], ["Chrome · Windows"])
        # A lista nunca devolve o token nem o hash dele.
        self.assertNotIn(desktop["Authorization"][7:], listed.text)
        self.assertNotIn(digest(desktop["Authorization"][7:]), listed.text)
        phone_id = next(d["id"] for d in devices if not d["current"])

        other = self.register("outra@example.com")
        self.assertEqual(self.client.delete(f"/api/v1/auth/sessions/{phone_id}", headers=other).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=phone).status_code, 200)  # continua aberta

        self.assertEqual(self.client.delete(f"/api/v1/auth/sessions/{phone_id}", headers=desktop).status_code, 204)
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=phone).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=desktop).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/v1/auth/sessions/{phone_id}", headers=desktop).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/auth/sessions").status_code, 401)

    def test_logout_others_keeps_only_this_device(self):
        desktop = self.register()
        phone, tablet = self.login(), self.login()
        self.assertEqual(self.client.post("/api/v1/auth/logout-others", headers=desktop).status_code, 204)
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=desktop).status_code, 200)
        for gone in (phone, tablet):
            self.assertEqual(self.client.get("/api/v1/auth/me", headers=gone).status_code, 401)
        self.assertEqual(len(self.client.get("/api/v1/auth/sessions", headers=desktop).json()), 1)

    def test_session_cap_drops_the_oldest(self):
        first = self.register()
        with patch.object(get_settings(), "MAX_SESSIONS_PER_USER", 3):
            newer = [self.login() for _ in range(3)]
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=first).status_code, 401)
        for headers in newer:
            self.assertEqual(self.client.get("/api/v1/auth/me", headers=headers).status_code, 200)

    def test_customer_session_lasts_days_and_admin_session_hours(self):
        customer = self.register()
        with self.sessions() as db:
            session = db.get(AccountSession, digest(customer["Authorization"][7:]))
            lifetime = as_utc(session.expires_at) - as_utc(session.created_at)
            self.assertEqual(lifetime, timedelta(days=get_settings().SESSION_DAYS))
            db.scalar(select(User).where(User.email == "ana@example.com")).is_admin = True
            db.commit()
        boss = self.login()
        with self.sessions() as db:
            session = db.get(AccountSession, digest(boss["Authorization"][7:]))
            self.assertEqual(as_utc(session.expires_at) - as_utc(session.created_at),
                             timedelta(hours=get_settings().ADMIN_SESSION_HOURS))

    def test_old_session_cannot_use_admin_even_before_it_expires(self):
        self.assertEqual(self.client.get("/api/v1/admin/products", headers=self.admin_headers).status_code, 200)
        with self.sessions() as db:
            session = db.get(AccountSession, digest("admin-test-token"))
            session.created_at = utc_now() - timedelta(hours=get_settings().ADMIN_SESSION_HOURS, minutes=1)
            session.expires_at = utc_now() + timedelta(days=5)
            db.commit()
        stale = self.client.get("/api/v1/admin/products", headers=self.admin_headers)
        self.assertEqual(stale.status_code, 401)
        self.assertIn("administração expirou", stale.json()["detail"])
        # A conta continua valendo para a parte de cliente (ex.: ver o próprio perfil).
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=self.admin_headers).status_code, 200)

    def test_oversized_or_empty_token_is_rejected(self):
        for value in ("Bearer " + "a" * 5000, "Bearer ", "Basic abc", "a" * 64):
            self.assertEqual(self.client.get("/api/v1/auth/me", headers={"Authorization": value}).status_code, 401)

    def test_last_used_is_written_at_most_every_ten_minutes(self):
        headers = self.register()
        token_hash = digest(headers["Authorization"][7:])
        with self.sessions() as db:
            first = as_utc(db.get(AccountSession, token_hash).last_used_at)
        self.client.get("/api/v1/auth/me", headers=headers)
        with self.sessions() as db:
            self.assertEqual(as_utc(db.get(AccountSession, token_hash).last_used_at), first)  # recente: não regrava
            db.get(AccountSession, token_hash).last_used_at = utc_now() - timedelta(minutes=11)
            db.commit()
        self.client.get("/api/v1/auth/me", headers=headers)
        with self.sessions() as db:
            self.assertGreater(as_utc(db.get(AccountSession, token_hash).last_used_at), first - timedelta(seconds=1))
            self.assertGreater(as_utc(db.get(AccountSession, token_hash).last_used_at),
                               utc_now() - timedelta(minutes=1))

    def test_password_change_and_export_reflect_devices(self):
        desktop = self.register()
        phone = self.login()
        changed = self.client.post("/api/v1/users/me/password", headers=desktop,
                                   json={"current_password": PASSWORD, "new_password": "Outra frase segura 456!"})
        self.assertEqual(changed.status_code, 204)
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=phone).status_code, 401)
        export = self.client.post("/api/v1/users/me/data-export", headers=desktop,
                                  json={"password": "Outra frase segura 456!"}).json()
        self.assertEqual([s["device"] for s in export["sessions"]], ["Chrome · Windows"])
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(AccountSession).where(
                AccountSession.user_id == db.scalar(select(User.id).where(User.email == "ana@example.com")))), 1)


if __name__ == "__main__":
    unittest.main()
