from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.product import Product


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(self, skip: int = 0, limit: int = 20, category_id: int | None = None, search: str | None = None) -> list[Product]:
        statement = select(Product).options(selectinload(Product.category)).order_by(Product.id)

        if category_id is not None:
            statement = statement.where(Product.category_id == category_id)

        if search:
            statement = statement.where(Product.name.ilike(f"%{search}%"))

        statement = statement.offset(skip).limit(limit)
        return self.db.execute(statement).scalars().all()

    def get_by_id(self, product_id: int) -> Product | None:
        statement = (
            select(Product)
            .options(selectinload(Product.category))
            .where(Product.id == product_id)
        )
        return self.db.execute(statement).scalar_one_or_none()
