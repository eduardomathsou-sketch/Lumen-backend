from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.category import Category  # registra Category junto com Product (relação abaixo)
from app.models.product_variant import ProductVariant


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    description: Mapped[str | None] = mapped_column(String(500))
    # Ficha da peça (padrão das maisons): composição e cuidados ficam separados da descrição.
    composition: Mapped[str | None] = mapped_column(String(200))
    care: Mapped[str | None] = mapped_column(String(300))
    # Dinheiro sempre em centavos inteiros (R$ 39,90 = 3990): sem erro de arredondamento de float.
    price_cents: Mapped[int] = mapped_column(default=0, server_default="0")
    # Estoque disponível para novas compras (já descontadas as reservas de pedidos pendentes).
    stock: Mapped[int] = mapped_column(default=0)
    # Índice: a vitrine filtra por categoria.
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), index=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    image_url: Mapped[str | None] = mapped_column(String(2048))
    # Controle de concorrência otimista: toda edição, reserva ou liberação soma 1.
    version: Mapped[int] = mapped_column(default=0, server_default="0")
    weight_grams: Mapped[int] = mapped_column(default=500, server_default="500")
    height_cm: Mapped[int] = mapped_column(default=10, server_default="10")
    width_cm: Mapped[int] = mapped_column(default=15, server_default="15")
    length_cm: Mapped[int] = mapped_column(default=20, server_default="20")

    category: Mapped[Category | None] = relationship(back_populates="products")
    variants: Mapped[list[ProductVariant]] = relationship(order_by=ProductVariant.id, lazy="selectin")

    @property
    def active_variants(self) -> list[ProductVariant]:
        return [v for v in self.variants if v.is_active]

    @property
    def available_stock(self) -> int:
        """Com variações ativas, o estoque vendável é a soma delas; sem variações, o do produto."""
        variants = self.active_variants
        return sum(v.stock for v in variants) if variants else self.stock

    @property
    def price(self) -> float:
        """Preço em reais, só para exibição (a API pública mantém o campo `price`)."""
        return self.price_cents / 100
