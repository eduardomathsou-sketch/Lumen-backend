import unittest
from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import func, select

import test_checkout as checkout
from app.core.config import get_settings
from app.core.security import digest
from app.maintenance import cleanup
from app.models.account import AccountSession, AuthAttempt
from app.models.payment import utc_now
from app.models.user import User


class HardeningTests(unittest.TestCase):
    setUp = checkout.CheckoutTests.setUp
    tearDown = checkout.CheckoutTests.tearDown
    order = checkout.CheckoutTests.order
    stock = checkout.CheckoutTests.stock

    def test_cart_creation_is_rate_limited_per_ip(self):
        # setUp já criou uma sacola a partir do mesmo IP do cliente de testes.
        with patch.object(get_settings(), "CART_IP_LIMIT", 3):
            self.assertEqual(self.client.post("/api/v1/cart").status_code, 201)
            self.assertEqual(self.client.post("/api/v1/cart").status_code, 201)
            blocked = self.client.post("/api/v1/cart")
            self.assertEqual(blocked.status_code, 429)
            self.assertEqual(blocked.headers["Retry-After"], "900")

    def test_coupon_guessing_is_limited_but_valid_codes_do_not_count(self):
        import test_admin as admin
        admin.AdminTests.setUp(self)
        created = self.client.post("/api/v1/admin/coupons", headers=self.admin_headers,
                                   json={"code": "LUMEN10", "kind": "percent", "value": 10})
        self.assertEqual(created.status_code, 201, created.text)
        quote = lambda code: self.client.get(f"/api/v1/cart/quote?coupon={code}", headers=self.headers)
        with patch.object(get_settings(), "COUPON_ATTEMPT_LIMIT", 3):
            for _ in range(5):  # usar um cupom que existe nunca conta como tentativa
                self.assertEqual(quote("LUMEN10").status_code, 200)
            for guess in ("AAA111", "BBB222", "CCC333"):
                self.assertEqual(quote(guess).status_code, 422)
            blocked = quote("DDD444")
            self.assertEqual(blocked.status_code, 429)
            self.assertEqual(blocked.headers["Retry-After"], "900")
            # Bloqueado, nem o código certo responde: senão o bloqueio viraria um teste de códigos.
            self.assertEqual(quote("LUMEN10").status_code, 429)
            order = self.order(body={**self.body, "coupon_code": "EEE555"})
            self.assertEqual(order.status_code, 429)
            # Sem cupom a compra continua normal.
            self.assertEqual(self.client.get("/api/v1/cart/quote", headers=self.headers).status_code, 200)
            self.assertEqual(self.order().status_code, 201)

    def test_new_orders_are_rate_limited_per_ip(self):
        with patch.object(get_settings(), "ORDER_IP_LIMIT", 5):
            first = self.order()
            self.assertEqual(first.status_code, 201)
            for _ in range(4):  # repetir a mesma tentativa devolve o mesmo pedido
                self.assertEqual(self.order().json()["id"], first.json()["id"])
            blocked = self.order(key="another-key-123")
            self.assertEqual(blocked.status_code, 429)
        self.assertEqual(self.stock(), 1)  # 3 em estoque, 2 reservados só pelo primeiro pedido

    def test_units_per_item_are_capped(self):
        with self.sessions() as db:
            from app.models.product import Product
            db.get(Product, 1).stock = 50
            db.commit()
        version = self.client.get("/api/v1/cart", headers=self.headers).json()["version"]
        too_many = self.client.put("/api/v1/cart/items/1", headers=self.headers,
                                   json={"quantity": 11, "version": version})
        self.assertEqual(too_many.status_code, 422)
        self.assertIn("10 unidades", too_many.json()["detail"])
        allowed = self.client.put("/api/v1/cart/items/1", headers=self.headers,
                                  json={"quantity": 10, "version": version})
        self.assertEqual(allowed.status_code, 200)

    def test_cleanup_removes_only_expired_rows(self):
        with self.sessions() as db:
            user = User(email="limpeza@example.com", hashed_password="unused")
            db.add(user)
            db.flush()
            db.add_all([
                AccountSession(token_hash=digest("velha"), user_id=user.id, expires_at=utc_now() - timedelta(days=1)),
                AccountSession(token_hash=digest("valida"), user_id=user.id, expires_at=utc_now() + timedelta(days=1)),
                AuthAttempt(key=digest("antiga"), count=3, started_at=utc_now() - timedelta(hours=2)),
                AuthAttempt(key=digest("recente"), count=1, started_at=utc_now()),
            ])
            db.commit()
            removed = cleanup(db)
            self.assertEqual((removed["sessions"], removed["attempts"]), (1, 1))
            self.assertEqual(db.scalar(select(func.count()).select_from(AccountSession)), 1)
            self.assertEqual(db.get(AccountSession, digest("valida")).user_id, user.id)
            self.assertEqual(db.scalar(select(func.count()).select_from(AuthAttempt).where(
                AuthAttempt.key == digest("recente"))), 1)


if __name__ == "__main__":
    unittest.main()
