from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.product import ProductRead
from app.services.product_service import ProductService
from repositories.product_repository import ProductRepository

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductRead])
def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    category_id: int | None = Query(default=None),
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    repository = ProductRepository(db)
    service = ProductService(repository)
    products = service.list_products(skip=skip, limit=limit, category_id=category_id, search=search)

    return [
        ProductRead(
            id=product.id,
            name=product.name,
            description=product.description,
            price=product.price,
            stock=product.stock,
            category_id=product.category_id,
            category_name=product.category.name if product.category else None,
            is_active=product.is_active,
        )
        for product in products
    ]


@router.get("/{product_id}", response_model=ProductRead)
def get_product_by_id(
    product_id: int,
    db: Session = Depends(get_db),
):
    repository = ProductRepository(db)
    service = ProductService(repository)
    product = service.get_product(product_id)

    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    return ProductRead(
        id=product.id,
        name=product.name,
        description=product.description,
        price=product.price,
        stock=product.stock,
        category_id=product.category_id,
        category_name=product.category.name if product.category else None,
        is_active=product.is_active,
    )
