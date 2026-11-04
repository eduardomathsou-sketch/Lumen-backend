from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.payment import utc_now


class Coupon(Base):
    """Cupom de desconto: percentual (1 a 90%) ou valor fixo em centavos."""
    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)  # sempre em MAIÚSCULAS
    kind: Mapped[str] = mapped_column(String(10))  # "percent" ou "fixed"
    value: Mapped[int]  # percentual (ex.: 10) ou centavos (ex.: 1500 = R$ 15,00)
    min_subtotal_cents: Mapped[int] = mapped_column(default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_uses: Mapped[int | None]
    # Usos reservados por pedidos (devolvidos se o pedido for cancelado ou recusado).
    used_count: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)
    version: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
