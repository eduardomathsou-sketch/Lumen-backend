import hashlib
import hmac
import json
import os
import tempfile
import subprocess
import sys
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

# Tests never load production credentials or write the application's database.
os.environ.update(DEBUG="false", DATABASE_URL="sqlite://", PAYMENT_PROVIDER="sandbox", SHIPPING_PROVIDER="flat",
                  MELHOR_ENVIO_TOKEN="", MELHOR_ENVIO_USER_AGENT="",
                  PAYMENT_WEBHOOK_SECRET="test-secret", SHIPPING_FLAT_RATE_CENTS="1500")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.api.deps import get_db
from app.core.database import Base
from app.core.db_engine import build_engine, database_url
from app.core.config import get_settings
from app.models.payment import Payment
from app.models.order import Order
from app.models.product import Product
from app.services.payment_service import MercadoPagoProvider, PaymentProviderRequestError


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pg_admin = None
        if os.getenv("TEST_DATABASE_URL"):
            from sqlalchemy.schema import CreateSchema
            self.schema = "lumen_test_" + uuid.uuid4().hex
            self.pg_admin = build_engine(os.environ["TEST_DATABASE_URL"])
            with self.pg_admin.begin() as connection:
                connection.execute(CreateSchema(self.schema))
            url = database_url(os.environ["TEST_DATABASE_URL"]).update_query_dict({"options": f"-csearch_path={self.schema}"})
            self.engine = build_engine(url.render_as_string(hide_password=False))
            from alembic import command
            from alembic.config import Config
            with self.engine.begin() as connection:
                config = Config("alembic.ini")
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
        else:
            self.engine = create_engine(f"sqlite:///{Path(self.tmp.name) / 'test.db'}", connect_args={"check_same_thread": False})
            Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(self.engine, autoflush=False, expire_on_commit=False)
        def db_override():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = db_override
        self.client = TestClient(app)
        with self.sessions() as db:
            db.add(Product(id=1, name="Vestido", price=39.90, stock=3, is_active=True))
            db.add(Product(id=2, name="Bolsa", price=12.99, stock=0, is_active=True))
            db.commit()
        self.token = self.client.post("/api/v1/cart").json()["token"]
        self.headers = {"X-Cart-Token": self.token}
        self.client.put("/api/v1/cart/items/1", headers=self.headers, json={"quantity": 2, "version": 0})
        self.body = {
            "cart_version": 1, "expected_total_cents": 9480,
            "payer_email": "cliente@example.com", "payer_document": "52998224725",
            "address": {"recipient": "Cliente Teste", "postal_code": "01001000", "street": "Praça da Sé",
                        "number": "1", "district": "Sé", "city": "São Paulo", "state": "SP"},
        }

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()
        if self.pg_admin:
            from sqlalchemy.schema import DropSchema
            with self.pg_admin.begin() as connection:
                connection.execute(DropSchema(self.schema, cascade=True))
            self.pg_admin.dispose()
        self.tmp.cleanup()

    def order(self, key="checkout-key-1", body=None):
        return self.client.post("/api/v1/orders", headers={**self.headers, "Idempotency-Key": key}, json=body or self.body)

    def post(self, order_id, action):
        return self.client.post(f"/api/v1/orders/{order_id}/{action}", headers=self.headers)

    def stock(self):
        with self.sessions() as db:
            return db.get(Product, 1).stock

    def webhook(self, order, state="paid", event_id="event-1"):
        raw = json.dumps({"id": event_id, "type": "payment.updated", "data": {
            "provider_charge_id": order["payment"]["provider_charge_id"], "status": state}}).encode()
        signature = hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()
        return self.client.post("/api/v1/payments/webhooks/provider", content=raw,
                                headers={"X-Payment-Signature": signature})

    def test_checkout_payment_and_duplicate_confirmation(self):
        order = self.order().json()
        self.assertEqual(order["total_cents"], 9480)
        self.assertEqual(self.stock(), 1)
        charge = self.post(order["id"], "pix").json()
        self.assertTrue(charge["payment"]["next_action"]["sandbox"])
        self.assertEqual(self.webhook(charge).status_code, 200)
        self.assertEqual(self.webhook(charge).json()["status"], "duplicate")
        self.assertEqual(self.stock(), 1)
        actual = self.client.get(f"/api/v1/orders/{order['id']}", headers=self.headers).json()
        self.assertEqual(actual["status"], "paid")
        self.assertEqual(self.client.get("/api/v1/cart", headers=self.headers).json()["items"], [])

    def test_retries_create_one_order_and_one_payment(self):
        order = self.order().json()
        self.assertEqual(self.order().json()["id"], order["id"])
        first = self.post(order["id"], "pix").json()
        self.assertEqual(self.post(order["id"], "pix").json()["payment"], first["payment"])
        self.assertEqual(self.stock(), 1)
        with self.sessions() as db:
            self.assertEqual(len(db.scalars(select(Payment)).all()), 1)

    def test_concurrent_checkout_reserves_once(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda _: self.order(), range(2)))
        self.assertEqual([r.status_code for r in responses], [201, 201])
        self.assertEqual(responses[0].json()["id"], responses[1].json()["id"])
        self.assertEqual(self.stock(), 1)

    def test_price_tampering_rejected(self):
        self.assertEqual(self.order(body={**self.body, "amount": "0.01"}).status_code, 422)
        self.assertEqual(self.order(body={**self.body, "expected_total_cents": 1}).status_code, 409)
        self.assertEqual(self.stock(), 3)

    def test_stale_price_requires_review(self):
        with self.sessions() as db:
            db.get(Product, 1).price = 45
            db.commit()
        self.assertEqual(self.order().status_code, 409)
        self.assertEqual(self.stock(), 3)

    def test_cart_survives_new_client(self):
        with self.sessions() as db:
            db.get(Product, 1).image_url = 'https://images.example.com/vestido.png'
            db.commit()
        current = self.client.get('/api/v1/cart', headers=self.headers).json()
        self.assertEqual(current['items'][0]['image_url'], 'https://images.example.com/vestido.png')
        client = TestClient(app)
        try:
            result = client.get("/api/v1/cart", headers=self.headers)
            self.assertEqual(result.json()["items"][0]["quantity"], 2)
        finally:
            client.close()

    def test_other_session_cannot_read_or_pay_order(self):
        order = self.order().json()
        other = {"X-Cart-Token": self.client.post("/api/v1/cart").json()["token"]}
        self.assertEqual(self.client.get(f"/api/v1/orders/{order['id']}", headers=other).status_code, 404)
        self.assertEqual(self.client.post(f"/api/v1/orders/{order['id']}/pix", headers=other).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/cart").status_code, 401)

    def test_cancel_releases_stock_once(self):
        order = self.order().json()
        self.assertEqual(self.post(order["id"], "cancel").json()["status"], "cancelled")
        self.assertEqual(self.post(order["id"], "cancel").json()["status"], "cancelled")
        self.assertEqual(self.stock(), 3)

    def test_paid_cannot_be_cancelled_or_regressed(self):
        order = self.post(self.order().json()["id"], "pix").json()
        self.webhook(order)
        self.webhook(order, "pending", "late-event")
        self.assertEqual(self.post(order["id"], "cancel").json()["status"], "paid")
        self.assertEqual(self.stock(), 1)

    def test_pending_order_locks_cart(self):
        self.order()
        result = self.client.put("/api/v1/cart/items/1", headers=self.headers, json={"quantity": 0, "version": 2})
        self.assertEqual(result.status_code, 409)

    def test_invalid_document_and_insufficient_stock(self):
        self.assertEqual(self.order(body={**self.body, "payer_document": "11111111111"}).status_code, 422)
        response = self.client.put("/api/v1/cart/items/1", headers=self.headers, json={"quantity": 4, "version": 1})
        self.assertEqual(response.status_code, 409)

    def test_old_routes_and_reconciliation_are_not_public(self):
        self.assertEqual(self.client.post("/api/v1/payments/charges", json={"amount": 1}).status_code, 410)
        self.assertEqual(self.client.post("/api/v1/payments/reconcile").status_code, 401)

    def test_admin_reconciliation_verifies_and_confirms_live_payment(self):
        order = self.post(self.order().json()["id"], "pix").json()
        with self.sessions() as db:
            payment = db.scalar(select(Payment))
            payment.provider = "mercadopago"
            db.get(Order, order["id"]).provider = "mercadopago"
            db.commit()
        with patch.object(get_settings(), "PAYMENT_PROVIDER", "mercadopago"), \
             patch.object(get_settings(), "MERCADO_PAGO_ACCESS_TOKEN", "test-only-token"), \
             patch.object(get_settings(), "PAYMENT_ADMIN_TOKEN", "admin-test-only"), \
             patch.object(MercadoPagoProvider, "_request", return_value={
                 "id": order["payment"]["provider_charge_id"], "external_reference": order["id"],
                 "currency_id": "BRL", "transaction_amount": 94.80,
                 "payment_method_id": "pix", "status": "approved"}):
            response = self.client.post("/api/v1/payments/reconcile", headers={"Authorization": "Bearer admin-test-only"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["payments"][0]["status"], "paid")
        self.assertEqual(self.client.get(f"/api/v1/orders/{order['id']}", headers=self.headers).json()["status"], "paid")
        self.assertEqual(self.stock(), 1)

    def test_maintenance_runs_as_standalone_process_and_releases_expired_stock(self):
        from datetime import timedelta
        from app.models.payment import utc_now
        order = self.order().json()
        with self.sessions() as db:
            db.get(Order, order["id"]).expires_at = utc_now() - timedelta(minutes=1)
            db.commit()
        environment = {**os.environ, "DATABASE_URL": self.engine.url.render_as_string(hide_password=False)}
        result = subprocess.run([sys.executable, "-m", "app.maintenance"], env=environment,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.stock(), 3)

    def test_cors_accepts_checkout_headers(self):
        response = self.client.options("/api/v1/orders", headers={
            "Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-cart-token,idempotency-key,content-type"})
        self.assertEqual(response.status_code, 200)

    def test_live_payment_must_match_amount_and_order(self):
        order = self.post(self.order().json()["id"], "pix").json()
        from app.services.payment_service import PaymentService
        with self.sessions() as db:
            payment = db.scalar(select(Payment))
            payment.provider = "mercadopago"
            provider = MercadoPagoProvider("test-token")
            with patch.object(provider, "_request", return_value={"id": payment.provider_charge_id,
                    "external_reference": order["id"], "currency_id": "BRL", "transaction_amount": 1,
                    "payment_method_id": "pix", "status": "approved"}):
                with self.assertRaises(PaymentProviderRequestError):
                    PaymentService(db, provider).refresh_payment(payment)
            self.assertEqual(db.get(Order, order["id"]).status, "awaiting_payment")

    def test_expired_order_releases_stock(self):
        from datetime import timedelta
        from app.models.payment import utc_now
        order = self.order().json()
        with self.sessions() as db:
            db.get(Order, order["id"]).expires_at = utc_now() - timedelta(minutes=1)
            db.commit()
        self.assertEqual(self.post(order["id"], "refresh").json()["status"], "cancelled")
        self.assertEqual(self.stock(), 3)

    def test_timeout_retries_same_provider_key(self):
        from app.services.payment_service import SandboxPaymentProvider
        original = SandboxPaymentProvider.create_charge
        keys = []
        def uncertain(provider, charge, key):
            keys.append(key)
            result = original(provider, charge, key)
            if len(keys) == 1:
                raise PaymentProviderRequestError("Timeout after provider created payment")
            return result
        order = self.order().json()
        with patch.object(SandboxPaymentProvider, "create_charge", uncertain):
            self.assertEqual(self.post(order["id"], "pix").status_code, 502)
            self.assertEqual(self.post(order["id"], "pix").status_code, 200)
        self.assertEqual(keys[0], keys[1])
        self.assertEqual(self.stock(), 1)

    def test_refund_updates_paid_order_without_restocking_used_goods(self):
        order = self.post(self.order().json()["id"], "pix").json()
        self.webhook(order)
        self.webhook(order, "refunded", "refund-1")
        self.assertEqual(self.client.get(f"/api/v1/orders/{order['id']}", headers=self.headers).json()["status"], "refunded")
        self.assertEqual(self.stock(), 1)

    def test_sandbox_webhook_disabled_with_live_provider(self):
        with patch.object(get_settings(), "PAYMENT_PROVIDER", "mercadopago"):
            result = self.client.post("/api/v1/payments/webhooks/provider", json={})
            self.assertEqual(result.status_code, 404)

    def test_mercadopago_webhook_confirms_once_using_verified_resource(self):
        order = self.post(self.order().json()["id"], "pix").json()
        with self.sessions() as db:
            payment = db.scalar(select(Payment))
            payment.provider = "mercadopago"
            payment.provider_charge_id = "123456"
            db.get(Order, order["id"]).provider = "mercadopago"
            db.commit()
        signature = hmac.new(b"mp-test-secret", b"id:123456;request-id:request-1;ts:1704908010;", hashlib.sha256).hexdigest()
        headers = {"x-signature": f"ts=1704908010,v1={signature}", "x-request-id": "request-1"}
        with patch.object(get_settings(), "PAYMENT_PROVIDER", "mercadopago"), \
             patch.object(get_settings(), "MERCADO_PAGO_ACCESS_TOKEN", "test-only-token"), \
             patch.object(get_settings(), "MERCADO_PAGO_WEBHOOK_SECRET", "mp-test-secret"), \
             patch.object(MercadoPagoProvider, "_request", return_value={
                 "id": 123456, "external_reference": order["id"], "currency_id": "BRL",
                 "transaction_amount": 94.80, "payment_method_id": "pix", "status": "approved"}) as request:
            url = "/api/v1/payments/webhooks/mercadopago?data.id=123456"
            body = {"type": "payment", "data": {"id": "123456"}}
            self.assertEqual(self.client.post(url, headers=headers, json=body).json()["status"], "processed")
            self.assertEqual(self.client.post(url, headers=headers, json=body).json()["status"], "duplicate")
            request.assert_called_with("GET", "/v1/payments/123456")
            self.assertEqual(self.client.post(url, headers=headers, json={**body, "data": {"id": "654321"}}).status_code, 401)
        self.assertEqual(self.client.get(f"/api/v1/orders/{order['id']}", headers=self.headers).json()["status"], "paid")
        self.assertEqual(self.stock(), 1)

    def test_bad_signature_does_not_confirm_payment(self):
        order = self.post(self.order().json()["id"], "pix").json()
        result = self.client.post("/api/v1/payments/webhooks/provider", json={}, headers={"X-Payment-Signature": "bad"})
        self.assertEqual(result.status_code, 400)
        self.assertEqual(self.client.get(f"/api/v1/orders/{order['id']}", headers=self.headers).json()["status"], "awaiting_payment")

    def test_migration_adopts_existing_tables_without_deleting_catalog(self):
        from alembic import command
        from alembic.config import Config
        config = Config("alembic.ini")
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            command.upgrade(config, "head")
        self.assertEqual(self.stock(), 3)

    def test_migration_builds_fresh_database(self):
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import inspect
        engine = create_engine("sqlite://")
        try:
            config = Config("alembic.ini")
            with engine.begin() as connection:
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
                for table in Base.metadata.sorted_tables:
                    self.assertEqual(set(table.columns.keys()), {c["name"] for c in inspect(connection).get_columns(table.name)})
        finally:
            engine.dispose()
