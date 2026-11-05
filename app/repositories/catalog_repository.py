"""Acesso a dados de categorias e favoritos."""
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.account import Favorite
from app.models.category import Category
from app.models.product import Product


class CategoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[Category]:
        return list(self.db.scalars(select(Category).order_by(Category.name)))

    def get(self, category_id: int) -> Category | None:
        return self.db.get(Category, category_id)

    def name_exists(self, name: str) -> bool:
        return self.db.scalar(select(Category.id).where(func.lower(Category.name) == name.lower())) is not None

    def add(self, category: Category) -> Category:
        self.db.add(category)
        self.db.flush()
        return category


class FavoriteRepository:
    def __init__(self, db: Session):
        self.db = db

    def active_products(self, user_id: int) -> list[Product]:
        return list(self.db.scalars(
            select(Product).join(Favorite, Favorite.product_id == Product.id)
            .options(selectinload(Product.category))
            .where(Favorite.user_id == user_id, Product.is_active.is_(True)).order_by(Product.id)))

    def exists(self, user_id: int, product_id: int) -> bool:
        return self.db.get(Favorite, (user_id, product_id)) is not None

    def add(self, user_id: int, product_id: int) -> None:
        self.db.add(Favorite(user_id=user_id, product_id=product_id))
        self.db.flush()

    def remove(self, user_id: int, product_id: int) -> None:
        self.db.execute(delete(Favorite).where(Favorite.user_id == user_id, Favorite.product_id == product_id))
