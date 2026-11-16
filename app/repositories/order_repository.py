"""Acesso a dados de pedidos."""
from datetime import datetime

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models.order import Order
from app.utils.pagination import Page


class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, order_id: str) -> Order | None:
        return self.db.get(Order, order_id)

    def get_for_cart(self, order_id: str, cart_id: int) -> Order | None:
        return self.db.scalar(select(Order).where(Order.id == order_id, Order.cart_id == cart_id))

    def get_by_checkout_key(self, checkout_key: str) -> Order | None:
        return self.db.scalar(select(Order).where(Order.checkout_key == checkout_key))

    def list_for_cart(self, cart_id: int, page: Page) -> list[Order]:
        return list(self.db.scalars(select(Order).where(Order.cart_id == cart_id)
                                    .order_by(Order.created_at.desc()).offset(page.skip).limit(page.limit)))

    def add(self, order: Order) -> Order:
        self.db.add(order)
        return order

    def all_for_cart(self, cart_id: int) -> list[Order]:
        return list(self.db.scalars(select(Order).where(Order.cart_id == cart_id).order_by(Order.created_at)))

    def has_awaiting_payment(self, cart_id: int) -> bool:
        return self.db.scalar(select(Order.id).where(Order.cart_id == cart_id,
                                                     Order.status == "awaiting_payment").limit(1)) is not None

    def delivered_for_cart(self, cart_id: int) -> list[Order]:
        return list(self.db.scalars(select(Order).where(
            Order.cart_id == cart_id, Order.status == "paid", Order.fulfillment_status == "delivered")))

    def search(self, page: Page, status: str | None = None, fulfillment: str | None = None) -> list[Order]:
        """Lista do painel admin, mais recentes primeiro."""
        statement = select(Order).order_by(Order.created_at.desc(), Order.id)
        if status:
            statement = statement.where(Order.status == status)
        if fulfillment:
            statement = statement.where(Order.fulfillment_status == fulfillment)
        return list(self.db.scalars(statement.offset(page.skip).limit(page.limit)))

    # --- Manutenção (cron) ---
    @staticmethod
    def _due(cutoff: datetime):
        return or_(Order.maintenance_checked_at.is_(None), Order.maintenance_checked_at < cutoff)

    def pending_for_maintenance(self, cutoff: datetime, limit: int) -> list[str]:
        return list(self.db.scalars(select(Order.id).where(Order.status == "awaiting_payment", self._due(cutoff))
                                    .order_by(Order.maintenance_checked_at.asc().nullsfirst(),
                                              Order.created_at, Order.id).limit(limit)))

    def claim_for_maintenance(self, order_id: str, cutoff: datetime, now: datetime) -> bool:
        """Marca o pedido como visto; só um processo consegue (evita trabalho duplicado)."""
        result = self.db.execute(update(Order).where(
            Order.id == order_id, Order.status == "awaiting_payment", self._due(cutoff),
        ).values(maintenance_checked_at=now))
        return result.rowcount == 1
