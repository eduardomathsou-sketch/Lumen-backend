"""Regras do catálogo: vitrine pública, favoritos e gestão de produtos/categorias pelo admin."""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound, Unprocessable
from app.models.category import Category
from app.models.product import Product
from app.repositories.catalog_repository import CategoryRepository, FavoriteRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.admin import CategoryWrite, ProductEdit, ProductWrite
from app.schemas.product import ProductRead
from app.utils.pagination import Page


def public_read(product: Product) -> ProductRead:
    return ProductRead(
        id=product.id, name=product.name, description=product.description,
        price=product.price, price_cents=product.price_cents, stock=product.stock,
        category_id=product.category_id, category_name=product.category.name if product.category else None,
        image_url=product.image_url, is_active=product.is_active,
    )


def admin_read(product: Product) -> dict:
    return {
        'id': product.id, 'name': product.name, 'description': product.description,
        'price_cents': product.price_cents, 'stock': product.stock, 'category_id': product.category_id,
        'category_name': product.category.name if product.category else None,
        'image_url': product.image_url, 'is_active': product.is_active, 'version': product.version,
        'weight_grams': product.weight_grams, 'height_cm': product.height_cm,
        'width_cm': product.width_cm, 'length_cm': product.length_cm,
    }


class ProductService:
    def __init__(self, db: Session):
        self.db = db
        self.products = ProductRepository(db)
        self.categories = CategoryRepository(db)

    # --- Vitrine pública ---
    def list_products(self, page: Page, category_id: int | None = None, search: str | None = None) -> list[ProductRead]:
        return [public_read(p) for p in self.products.list_active(page, category_id, search)]

    def get_product(self, product_id: int) -> ProductRead:
        product = self.products.get_active(product_id)
        if product is None:
            raise NotFound("Produto não encontrado.")
        return public_read(product)

    def list_categories(self) -> list[dict]:
        return [{"id": c.id, "name": c.name, "description": c.description} for c in self.categories.list_all()]

    # --- Administração ---
    def admin_search(self, page: Page, search: str = "", is_active: bool | None = None) -> list[dict]:
        return [admin_read(p) for p in self.products.search_all(page, search, is_active)]

    def admin_get(self, product_id: int) -> dict:
        product = self.products.get(product_id)
        if product is None:
            raise NotFound("Produto não encontrado.")
        return admin_read(product)

    def _values(self, body: ProductWrite) -> dict:
        if body.category_id is not None and self.categories.get(body.category_id) is None:
            raise Unprocessable("Categoria não encontrada. Atualize a lista.")
        return body.model_dump(mode="json", exclude={"version"})

    def create(self, body: ProductWrite) -> dict:
        product = self.products.add(Product(**self._values(body)))
        self.db.commit()
        self.db.refresh(product)
        return admin_read(product)

    def edit(self, product_id: int, body: ProductEdit) -> dict:
        values = self._values(body)
        if not self.products.update_if_version(product_id, body.version, values):
            self.db.rollback()
            if self.products.get(product_id) is None:
                raise NotFound("Produto não encontrado.")
            raise Conflict("O produto ou estoque mudou. Recarregue os dados antes de salvar.")
        self.db.commit()
        product = self.products.get(product_id)
        self.db.refresh(product)
        return admin_read(product)

    def create_category(self, body: CategoryWrite) -> dict:
        if self.categories.name_exists(body.name):
            raise Conflict("Já existe uma categoria com esse nome.")
        try:
            category = self.categories.add(Category(**body.model_dump()))
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise Conflict("Já existe uma categoria com esse nome.") from exc
        return {"id": category.id, "name": category.name, "description": category.description}


class FavoriteService:
    def __init__(self, db: Session):
        self.db = db
        self.favorites = FavoriteRepository(db)
        self.products = ProductRepository(db)

    def list(self, user_id: int) -> list[ProductRead]:
        return [public_read(p) for p in self.favorites.active_products(user_id)]

    def add(self, user_id: int, product_id: int) -> None:
        product = self.products.get(product_id)
        if not product or not product.is_active:
            raise NotFound("Produto não encontrado.")
        if not self.favorites.exists(user_id, product_id):
            try:
                self.favorites.add(user_id, product_id)
                self.db.commit()
            except IntegrityError:
                self.db.rollback()

    def remove(self, user_id: int, product_id: int) -> None:
        self.favorites.remove(user_id, product_id)
        self.db.commit()
