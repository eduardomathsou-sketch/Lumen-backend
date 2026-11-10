from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.payment import utc_now


class Address(Base):
    """Endereço salvo na conta. O pedido guarda uma cópia (foto) do endereço usado na compra."""
    __tablename__ = "addresses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    label: Mapped[str] = mapped_column(String(40), default="Casa")
    recipient: Mapped[str] = mapped_column(String(120))
    postal_code: Mapped[str] = mapped_column(String(8))
    street: Mapped[str] = mapped_column(String(150))
    number: Mapped[str] = mapped_column(String(20))
    complement: Mapped[str] = mapped_column(String(100), default="")
    district: Mapped[str] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(2))
    is_default: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    def snapshot(self) -> dict:
        """Mesmo formato do endereço digitado no checkout (AddressWrite)."""
        return {"recipient": self.recipient, "postal_code": self.postal_code, "street": self.street,
                "number": self.number, "complement": self.complement, "district": self.district,
                "city": self.city, "state": self.state}
