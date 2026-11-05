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

    def test_cart_creation_is_rate_limited_per_ip(self):
        # setUp já criou uma sacola a partir do mesmo IP do cliente de testes.
        with patch.object(get_settings(), "CART_IP_LIMIT", 3):
            self.assertEqual(self.client.post("/api/v1/cart").status_code, 201)
            self.assertEqual(self.client.post("/api/v1/cart").status_code, 201)
            blocked = self.client.post("/api/v1/cart")
            self.assertEqual(blocked.status_code, 429)
            self.assertEqual(blocked.headers["Retry-After"], "900")

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
