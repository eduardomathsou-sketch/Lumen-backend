"""Payment orchestration.

The default provider is deliberately a sandbox adapter.  A production provider
must implement ``PaymentProvider`` and exchange only tokenized card data.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.payment import Payment, PaymentWebhookEvent
from app.schemas.payment import ChargeCreate, ProviderWebhook, ReconciliationItem, ReconciliationResult
from app.core.config import get_settings


class PaymentConflictError(Exception):
    pass


class InvalidWebhookError(Exception):
    pass


class PaymentProviderError(Exception):
    pass


class PaymentProviderConfigurationError(PaymentProviderError):
    pass


class PaymentProviderRequestError(PaymentProviderError):
    pass


class PaymentProvider(Protocol):
    name: str

    def create_charge(self, charge: ChargeCreate, idempotency_key: str) -> tuple[str, dict]: ...

    def get_charge_status(self, charge_id: str) -> str | None: ...


class SandboxPaymentProvider:
    """Safe local provider used until a real acquirer adapter is configured."""

    name = "sandbox"
    _charges: dict[str, str] = {}

    def create_charge(self, charge: ChargeCreate, idempotency_key: str) -> tuple[str, dict]:
        charge_id = f"sandbox_{hashlib.sha256(idempotency_key.encode()).hexdigest()[:32]}"
        self._charges[charge_id] = "pending"
        if charge.method == "pix":
            return charge_id, {
                "type": "pix",
                "sandbox": True,
                "copy_and_paste": f"LUMENPIX:{charge_id}:{charge.amount:.2f}:{charge.currency}",
            }
        # A token is only checked for presence. It is never persisted or logged.
        return charge_id, {"type": "redirect", "message": "Awaiting provider authorization"}

    def get_charge_status(self, charge_id: str) -> str | None:
        return self._charges.get(charge_id)

    def record_webhook_status(self, charge_id: str, status: str) -> None:
        if charge_id in self._charges:
            self._charges[charge_id] = status


class MercadoPagoProvider:
    """Mercado Pago Payments API adapter for live PIX payments."""

    name = "mercadopago"
    api_base_url = "https://api.mercadopago.com"

    def __init__(self, access_token: str, notification_url: str = ""):
        if not access_token:
            raise PaymentProviderConfigurationError("MERCADO_PAGO_ACCESS_TOKEN is not configured")
        self.access_token = access_token
        self.notification_url = notification_url

    def _request(self, method: str, path: str, **kwargs) -> dict:
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.access_token}"
        try:
            with httpx.Client(base_url=self.api_base_url, timeout=15.0) as client:
                response = client.request(method, path, headers=headers, **kwargs)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PaymentProviderRequestError("Mercado Pago request could not be completed") from exc

    def create_charge(self, charge: ChargeCreate, idempotency_key: str) -> tuple[str, dict]:
        if charge.method != "pix":
            raise PaymentProviderError("Mercado Pago live adapter currently supports PIX only")
        if not charge.payer_email or not charge.payer_document:
            raise PaymentProviderError("payer_email and payer_document are required to generate a PIX")

        document_type = "CPF" if len(charge.payer_document) == 11 else "CNPJ"
        body = {
            "transaction_amount": float(charge.amount),
            "description": f"Pedido {charge.order_reference}",
            "payment_method_id": "pix",
            "external_reference": charge.order_reference,
            "payer": {
                "email": charge.payer_email,
                "identification": {"type": document_type, "number": charge.payer_document},
            },
        }
        if self.notification_url:
            body["notification_url"] = self.notification_url
        result = self._request(
            "POST",
            "/v1/payments",
            headers={"X-Idempotency-Key": idempotency_key},
            json=body,
        )
        transaction_data = result.get("point_of_interaction", {}).get("transaction_data", {})
        payment_id = result.get("id")
        pix_code = transaction_data.get("qr_code")
        if not payment_id or not pix_code:
            raise PaymentProviderRequestError("Mercado Pago did not return the PIX payment data")
        provider_data = {
            "type": "pix",
            "copy_and_paste": pix_code,
            "qr_code_base64": transaction_data.get("qr_code_base64"),
            "ticket_url": transaction_data.get("ticket_url"),
        }
        return str(payment_id), provider_data

    def get_charge_status(self, charge_id: str) -> str | None:
        result = self._request("GET", f"/v1/payments/{charge_id}")
        return self.map_status(result.get("status"))

    def get_payment_status(self, charge_id: str) -> str:
        status = self.get_charge_status(charge_id)
        if not status:
            raise PaymentProviderRequestError("Mercado Pago returned a payment without a status")
        return status

    @staticmethod
    def map_status(status: str | None) -> str | None:
        return {
            "approved": "paid",
            "rejected": "failed",
            "cancelled": "cancelled",
            "canceled": "cancelled",
            "expired": "cancelled",
            "refunded": "refunded",
            "pending": "pending",
            "in_process": "pending",
            "in_mediation": "pending",
        }.get(status)

    @staticmethod
    def verify_webhook_signature(
        x_signature: str | None, x_request_id: str | None, data_id: str | None, secret: str
    ) -> None:
        if not x_signature or not data_id or not secret:
            raise InvalidWebhookError("Missing Mercado Pago webhook signature data")
        signature_parts = {}
        for part in x_signature.split(","):
            key, separator, value = part.strip().partition("=")
            if separator:
                signature_parts[key] = value
        timestamp = signature_parts.get("ts")
        received_hash = signature_parts.get("v1")
        if not timestamp or not received_hash or not received_hash.isascii():
            raise InvalidWebhookError("Invalid Mercado Pago webhook signature")
        manifest = f"id:{data_id.lower()};"
        if x_request_id:
            manifest += f"request-id:{x_request_id};"
        manifest += f"ts:{timestamp};"
        expected_hash = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(received_hash, expected_hash):
            raise InvalidWebhookError("Invalid Mercado Pago webhook signature")


def default_payment_provider() -> PaymentProvider:
    settings = get_settings()
    provider_name = settings.PAYMENT_PROVIDER.lower()
    if provider_name == "sandbox":
        return SandboxPaymentProvider()
    if provider_name == "mercadopago":
        return MercadoPagoProvider(
            access_token=settings.MERCADO_PAGO_ACCESS_TOKEN,
            notification_url=settings.MERCADO_PAGO_NOTIFICATION_URL,
        )
    raise PaymentProviderConfigurationError(f"Unsupported payment provider: {provider_name}")


def _fingerprint(charge: ChargeCreate) -> str:
    data = {
        "order_reference": charge.order_reference,
        "amount": format(charge.amount, '.2f'),
        "currency": charge.currency,
        "method": charge.method,
        "payer_email": charge.payer_email,
        "payer_document": charge.payer_document,
        # The token must affect idempotency but must not be stored.
        "card_token_digest": hashlib.sha256((charge.card_token or "").encode()).hexdigest(),
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


class PaymentService:
    def __init__(self, db: Session, provider: PaymentProvider | None = None):
        self.db = db
        self.provider = provider or default_payment_provider()

    def create_charge(self, charge: ChargeCreate, idempotency_key: str, *, commit=True) -> tuple[Payment, bool]:
        fingerprint = _fingerprint(charge)
        existing = self.db.scalar(select(Payment).where(Payment.idempotency_key == idempotency_key))
        if existing:
            if existing.request_fingerprint != fingerprint:
                raise PaymentConflictError("Idempotency-Key was already used with a different request")
            return existing, True

        charge_id, provider_data = self.provider.create_charge(charge, idempotency_key)
        payment = Payment(
            order_reference=charge.order_reference,
            amount=charge.amount,
            currency=charge.currency,
            method=charge.method,
            status="pending",
            provider=self.provider.name,
            provider_charge_id=charge_id,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            provider_data=provider_data,
        )
        self.db.add(payment)
        try:
            self.db.flush()
            if commit:
                self.db.commit()
        except IntegrityError:
            # A simultaneous retry may have won the unique-key race.
            self.db.rollback()
            existing = self.db.scalar(select(Payment).where(Payment.idempotency_key == idempotency_key))
            if existing and existing.request_fingerprint == fingerprint:
                return existing, True
            raise PaymentConflictError("Could not create an idempotent payment")
        self.db.refresh(payment)
        return payment, False

    def get_charge(self, provider_charge_id: str) -> Payment | None:
        return self.db.scalar(
            select(Payment).where(Payment.provider_charge_id == provider_charge_id)
        )

    @staticmethod
    def verify_webhook_signature(raw_body: bytes, signature: str | None, secret: str) -> None:
        if not signature:
            raise InvalidWebhookError("Missing X-Payment-Signature")
        supplied = signature.removeprefix("sha256=")
        if not supplied.isascii():
            raise InvalidWebhookError("Invalid webhook signature")
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(supplied, expected):
            raise InvalidWebhookError("Invalid webhook signature")

    def process_webhook(self, event: ProviderWebhook) -> tuple[Payment, bool]:
        prior = self.db.scalar(
            select(PaymentWebhookEvent).where(PaymentWebhookEvent.provider_event_id == event.id)
        )
        if prior:
            return prior.payment, True

        payment = self.db.scalar(
            select(Payment).where(Payment.provider_charge_id == event.data.provider_charge_id)
        )
        if not payment:
            raise InvalidWebhookError("Payment charge was not found")

        webhook_event = PaymentWebhookEvent(
            provider_event_id=event.id,
            payment_id=payment.id,
            event_type=event.type,
            payload=event.model_dump(mode="json"),
        )
        self.db.add(webhook_event)
        if isinstance(self.provider, SandboxPaymentProvider):
            self.provider.record_webhook_status(event.data.provider_charge_id, event.data.status)
        self._apply_status(payment, event.data.status)
        webhook_event.processed_at = datetime.now(timezone.utc)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            prior = self.db.scalar(
                select(PaymentWebhookEvent).where(PaymentWebhookEvent.provider_event_id == event.id)
            )
            if prior:
                return prior.payment, True
            raise
        self.db.refresh(payment)
        return payment, False

    def _apply_status(self, payment: Payment, new_status: str) -> None:
        # A late pending/failed event must never undo a confirmed payment.
        if payment.status == "refunded":
            return
        if payment.status == "paid" and new_status not in {"paid", "refunded"}:
            return
        if payment.status in {"failed", "cancelled"} and new_status == "pending":
            return
        payment.status = new_status
        if new_status == "paid" and not payment.paid_at:
            payment.paid_at = datetime.now(timezone.utc)
        from app.services.commerce_service import sync_order
        sync_order(self.db, payment)

    def refresh_payment(self, payment: Payment):
        if payment.provider != self.provider.name:
            raise PaymentProviderRequestError("Provedor do pagamento indisponível.")
        if isinstance(self.provider, MercadoPagoProvider):
            result = self.provider._request("GET", f"/v1/payments/{payment.provider_charge_id}")
            try:
                matches = (str(result["id"]) == payment.provider_charge_id
                           and result["external_reference"] == payment.order_reference
                           and result["currency_id"] == payment.currency
                           and Decimal(str(result["transaction_amount"])) == payment.amount
                           and result["payment_method_id"] == "pix")
            except (KeyError, ValueError, TypeError):
                matches = False
            if not matches:
                raise PaymentProviderRequestError("Pagamento não corresponde ao pedido e valor esperado.")
            provider_status = self.provider.map_status(result.get("status"))
            if not provider_status:
                raise PaymentProviderRequestError("Status de pagamento requer revisão.")
            self._apply_status(payment, provider_status)
        return payment

    def reconcile(self) -> ReconciliationResult:
        from app.models.cart import Cart
        from app.models.order import Order
        from app.services.commerce_service import lock_cart

        payment_ids = self.db.scalars(select(Payment.id).where(
            Payment.provider == self.provider.name
        ).order_by(Payment.created_at.desc())).all()
        items: list[ReconciliationItem] = []
        for payment_id in payment_ids:
            payment = self.db.get(Payment, payment_id)
            order = self.db.get(Order, payment.order_reference)
            if order:
                lock_cart(self.db, self.db.get(Cart, order.cart_id))
                self.db.refresh(payment)
            reason = None
            previous_status = payment.status
            if isinstance(self.provider, MercadoPagoProvider):
                self.refresh_payment(payment)
            if previous_status != payment.status:
                reason = "Local status was updated from the provider"
            elif payment.status == "pending":
                reason = "Awaiting a signed provider webhook"
            elif payment.status not in {"paid", "failed", "cancelled", "refunded"}:
                reason = "Unknown local payment status"
            items.append(
                ReconciliationItem(
                    payment_id=payment.id,
                    provider_charge_id=payment.provider_charge_id,
                    status=payment.status,
                    result="needs_attention" if reason else "ok",
                    reason=reason,
                )
            )
            # Release each cart lock before moving to another checkout.
            self.db.commit()
        attention = sum(item.result == "needs_attention" for item in items)
        return ReconciliationResult(checked=len(items), needs_attention=attention, payments=items)
