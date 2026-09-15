from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.payment import utc_now


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    cart_id: Mapped[int] = mapped_column(ForeignKey("carts.id"), index=True)
    checkout_key: Mapped[str] = mapped_column(String(64), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    items: Mapped[list] = mapped_column(JSON)
    address: Mapped[dict] = mapped_column(JSON)
    payer_email: Mapped[str] = mapped_column(String(255))
    payer_document: Mapped[str] = mapped_column(String(14))
    subtotal_cents: Mapped[int]
    shipping_cents: Mapped[int]
    total_cents: Mapped[int]
    shipping_label: Mapped[str] = mapped_column(String(100))
    shipping_days: Mapped[int]
    provider: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="awaiting_payment", index=True)
    stock_released: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
