from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProductVariant(Base):
    """Variação de um produto (tamanho e/ou cor) com estoque próprio.

    Produto sem variações vende pelo estoque do próprio produto; produto com variações
    ativas exige escolher a variação, e a reserva sai do estoque dela.
    """
    __tablename__ = "product_variants"
    __table_args__ = (UniqueConstraint("product_id", "size", "color", name="uq_variant_product_size_color"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    size: Mapped[str] = mapped_column(String(20), default="")
    color: Mapped[str] = mapped_column(String(40), default="")
    stock: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)
    version: Mapped[int] = mapped_column(default=0, server_default="0")

    @property
    def label(self) -> str:
        return " / ".join(part for part in (self.size, self.color) if part)
