"""Acesso a dados de produtos. Nenhuma regra de negócio aqui: só consultas e escritas."""
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.models.product import Product
from app.utils.pagination import Page


def like_pattern(text: str) -> str:
    """Busca por trecho escapando % e _, para a cliente não montar curingas."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_active(self, page: Page, category_id: int | None = None, search: str | None = None) -> list[Product]:
        statement = (select(Product).where(Product.is_active.is_(True))
                     .options(selectinload(Product.category)).order_by(Product.id))
        if category_id is not None:
            statement = statement.where(Product.category_id == category_id)
        if search and search.strip():
            statement = statement.where(Product.name.ilike(like_pattern(search.strip()), escape="\\"))
        return list(self.db.scalars(statement.offset(page.skip).limit(page.limit)))

    def get_active(self, product_id: int) -> Product | None:
        return self.db.scalar(select(Product).options(selectinload(Product.category))
                              .where(Product.id == product_id, Product.is_active.is_(True)))

    def get(self, product_id: int) -> Product | None:
        return self.db.get(Product, product_id)

    def get_many(self, product_ids) -> dict[int, Product]:
        """Busca vários produtos numa consulta só (evita N+1 ao montar a sacola)."""
        ids = set(product_ids)
        if not ids:
            return {}
        rows = self.db.scalars(select(Product).options(selectinload(Product.category)).where(Product.id.in_(ids)))
        return {product.id: product for product in rows}

    def search_all(self, page: Page, search: str = "", is_active: bool | None = None) -> list[Product]:
        statement = select(Product).options(selectinload(Product.category)).order_by(Product.id.desc())
        if search.strip():
            statement = statement.where(Product.name.ilike(like_pattern(search.strip()), escape="\\"))
        if is_active is not None:
            statement = statement.where(Product.is_active.is_(is_active))
        return list(self.db.scalars(statement.offset(page.skip).limit(page.limit)))

    def add(self, product: Product) -> Product:
        self.db.add(product)
        self.db.flush()
        return product

    def update_if_version(self, product_id: int, version: int, values: dict) -> bool:
        """UPDATE ... WHERE version = ?: falha (False) se alguém mudou o produto depois da leitura."""
        result = self.db.execute(update(Product).where(Product.id == product_id, Product.version == version)
                                 .values(**values, version=Product.version + 1))
        return result.rowcount == 1

    def reserve(self, product_id: int, quantity: int) -> bool:
        """Testa e baixa o estoque numa instrução só (atômica): duas compras não levam a mesma unidade."""
        result = self.db.execute(update(Product).where(
            Product.id == product_id, Product.is_active.is_(True), Product.stock >= quantity,
        ).values(stock=Product.stock - quantity, version=Product.version + 1))
        return result.rowcount == 1

    def release(self, product_id: int, quantity: int) -> None:
        self.db.execute(update(Product).where(Product.id == product_id)
                        .values(stock=Product.stock + quantity, version=Product.version + 1))
