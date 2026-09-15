import hashlib
import hmac
import json
import unittest

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.payment import Payment
from app.schemas.payment import ChargeCreate, ProviderWebhook
from app.services.payment_service import MercadoPagoProvider, PaymentConflictError, PaymentService, SandboxPaymentProvider


class PaymentServiceTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        self.engine = engine
        Base.metadata.create_all(engine)
        self.session = sessionmaker(bind=engine, expire_on_commit=False)()
        self.service = PaymentService(self.session, SandboxPaymentProvider())

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_create_charge_replays_same_idempotency_key(self):
        request = ChargeCreate(order_reference="ORDER-1", amount="39.90", method="pix")
        payment, replayed = self.service.create_charge(request, "idempotency-key-1")
        again, replayed_again = self.service.create_charge(request, "idempotency-key-1")

        self.assertFalse(replayed)
        self.assertTrue(replayed_again)
        self.assertEqual(payment.id, again.id)
        self.assertEqual(self.session.query(Payment).count(), 1)

    def test_rejects_reuse_of_key_with_different_request(self):
        self.service.create_charge(
            ChargeCreate(order_reference="ORDER-1", amount="39.90", method="pix"), "idempotency-key-2"
        )
        with self.assertRaises(PaymentConflictError):
            self.service.create_charge(
                ChargeCreate(order_reference="ORDER-1", amount="40.00", method="pix"), "idempotency-key-2"
            )

    def test_card_requires_a_token_not_raw_card_data(self):
        with self.assertRaises(ValidationError):
            ChargeCreate(order_reference="ORDER-1", amount="39.90", method="card")
        with self.assertRaises(ValidationError):
            ChargeCreate(
                order_reference="ORDER-1",
                amount="39.90",
                method="card",
                card_token="token-12345678",
                card_number="4111111111111111",
            )

    def test_signed_webhook_confirms_payment_and_deduplicates_event(self):
        payment, _ = self.service.create_charge(
            ChargeCreate(order_reference="ORDER-1", amount="39.90", method="pix"), "idempotency-key-3"
        )
        raw = json.dumps(
            {
                "id": "event-1",
                "type": "payment.updated",
                "data": {"provider_charge_id": payment.provider_charge_id, "status": "paid"},
            },
            separators=(",", ":"),
        ).encode()
        signature = hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()
        self.service.verify_webhook_signature(raw, signature, "test-secret")

        processed, duplicate = self.service.process_webhook(ProviderWebhook.model_validate_json(raw))
        repeated, repeated_duplicate = self.service.process_webhook(ProviderWebhook.model_validate_json(raw))

        self.assertEqual(processed.status, "paid")
        self.assertFalse(duplicate)
        self.assertEqual(repeated.id, processed.id)
        self.assertTrue(repeated_duplicate)

    def test_mercado_pago_signature_is_verified(self):
        manifest = "id:123456;request-id:req-1;ts:1704908010;"
        signature = hmac.new(b"mp-secret", manifest.encode(), hashlib.sha256).hexdigest()
        MercadoPagoProvider.verify_webhook_signature(
            f"ts=1704908010,v1={signature}", "req-1", "123456", "mp-secret"
        )
