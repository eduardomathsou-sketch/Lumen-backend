from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db
from app.schemas.product import ProductRead
from app.schemas.review import ReviewWrite
from app.services import review_service
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


@router.get("/{product_id}/reviews")
def reviews(product_id: int, page: Page = Depends(page_params), db: Session = Depends(get_db)):
    return review_service.list_reviews(db, product_id, page)


@router.put("/{product_id}/reviews/me")
def save_review(product_id: int, body: ReviewWrite, user=Depends(current_user), db: Session = Depends(get_db)):
    return review_service.save_review(db, user, product_id, body)


@router.delete("/{product_id}/reviews/me", status_code=204)
def delete_review(product_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
    review_service.delete_review(db, user, product_id)
