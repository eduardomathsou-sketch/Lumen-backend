"""Acesso a dados de cobranças e dos avisos (webhooks) já processados."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.payment import Payment, PaymentWebhookEvent


class PaymentRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, payment_id: int) -> Payment | None:
        return self.db.get(Payment, payment_id)

    def by_idempotency_key(self, key: str) -> Payment | None:
        return self.db.scalar(select(Payment).where(Payment.idempotency_key == key))

    def by_charge_id(self, charge_id: str) -> Payment | None:
        return self.db.scalar(select(Payment).where(Payment.provider_charge_id == charge_id))

    def by_order(self, order_id: str) -> Payment | None:
        return self.db.scalar(select(Payment).where(Payment.order_reference == order_id))

    def ids_for_provider(self, provider: str) -> list[int]:
        return list(self.db.scalars(select(Payment.id).where(Payment.provider == provider)
                                    .order_by(Payment.created_at.desc())))

    def add(self, payment: Payment) -> Payment:
        self.db.add(payment)
        return payment

    def event(self, provider_event_id: str) -> PaymentWebhookEvent | None:
        return self.db.scalar(select(PaymentWebhookEvent).where(PaymentWebhookEvent.provider_event_id == provider_event_id))

    def add_event(self, event: PaymentWebhookEvent) -> PaymentWebhookEvent:
        self.db.add(event)
        return event
