"""Acesso a dados das cotações de frete."""
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.shipping import ShippingQuote


class ShippingQuoteRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, quote_id: str) -> ShippingQuote | None:
        return self.db.get(ShippingQuote, quote_id)

    def find_valid(self, cart_id: int, fingerprint: str, now: datetime) -> ShippingQuote | None:
        return self.db.scalar(select(ShippingQuote).where(
            ShippingQuote.cart_id == cart_id, ShippingQuote.fingerprint == fingerprint,
            ShippingQuote.expires_at > now).order_by(ShippingQuote.expires_at.desc()))

    def delete_expired(self, cart_id: int, now: datetime) -> None:
        self.db.execute(delete(ShippingQuote).where(ShippingQuote.cart_id == cart_id, ShippingQuote.expires_at < now))

    def add(self, quote: ShippingQuote) -> ShippingQuote:
        self.db.add(quote)
        return quote
