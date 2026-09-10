from repositories.product_repository import ProductRepository


class ProductService:
    def __init__(self, repository: ProductRepository):
        self.repository = repository

    def list_products(self, skip: int = 0, limit: int = 20, category_id: int | None = None, search: str | None = None):
        return self.repository.list(skip=skip, limit=limit, category_id=category_id, search=search)

    def get_product(self, product_id: int):
        return self.repository.get_by_id(product_id)
