from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.product import ProductRead
from app.services.product_service import ProductService
from app.utils.pagination import Page, page_params

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductRead])
def list_products(page: Page = Depends(page_params), category_id: int | None = Query(default=None),
                  search: str | None = Query(default=None, max_length=150), db: Session = Depends(get_db)):
    return ProductService(db).list_products(page, category_id, search)


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, db: Session = Depends(get_db)):
    return ProductService(db).get_product(product_id)
