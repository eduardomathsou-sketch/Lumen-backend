from datetime import datetime
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class ShippingQuote(Base):
    __tablename__ = 'shipping_quotes'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cart_id: Mapped[int] = mapped_column(ForeignKey('carts.id'), index=True)
    postal_code: Mapped[str] = mapped_column(String(8))
    fingerprint: Mapped[str] = mapped_column(String(64))
    options: Mapped[list] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
