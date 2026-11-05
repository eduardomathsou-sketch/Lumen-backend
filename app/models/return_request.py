from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.payment import utc_now


class ReturnRequest(Base):
    """Devolução de um pedido entregue (CDC: 7 dias por arrependimento, 90 por defeito).

    requested -> approved -> refunded
              -> rejected
    """
    __tablename__ = "return_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Uma solicitação por pedido (o pedido inteiro volta; troca = devolução + nova compra).
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True, index=True)
    reason: Mapped[str] = mapped_column(String(20))
    details: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="requested", index=True)
    admin_note: Mapped[str | None] = mapped_column(String(300))
    restocked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
