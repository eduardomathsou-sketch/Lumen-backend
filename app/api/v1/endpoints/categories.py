from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services.product_service import ProductService

router = APIRouter(prefix="/categories", tags=["catalog"])


@router.get("")
def categories(db: Session = Depends(get_db)):
    return ProductService(db).list_categories()
