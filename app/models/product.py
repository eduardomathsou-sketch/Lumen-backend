from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.category import Category  # registra Category junto com Product (relação abaixo)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    description: Mapped[str | None] = mapped_column(String(500))
    # Dinheiro sempre em centavos inteiros (R$ 39,90 = 3990): sem erro de arredondamento de float.
    price_cents: Mapped[int] = mapped_column(default=0, server_default="0")
    # Estoque disponível para novas compras (já descontadas as reservas de pedidos pendentes).
    stock: Mapped[int] = mapped_column(default=0)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    is_active: Mapped[bool] = mapped_column(default=True)
    image_url: Mapped[str | None] = mapped_column(String(2048))
    # Controle de concorrência otimista: toda edição, reserva ou liberação soma 1.
    version: Mapped[int] = mapped_column(default=0, server_default="0")
    weight_grams: Mapped[int] = mapped_column(default=500, server_default="500")
    height_cm: Mapped[int] = mapped_column(default=10, server_default="10")
    width_cm: Mapped[int] = mapped_column(default=15, server_default="15")
    length_cm: Mapped[int] = mapped_column(default=20, server_default="20")

    category: Mapped[Category | None] = relationship(back_populates="products")

    @property
    def price(self) -> float:
        """Preço em reais, só para exibição (a API pública mantém o campo `price`)."""
        return self.price_cents / 100
