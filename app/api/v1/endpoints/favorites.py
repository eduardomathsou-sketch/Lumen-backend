from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db
from app.schemas.product import ProductRead
from app.services.product_service import FavoriteService

router = APIRouter(prefix="/favorites", tags=["catalog"])


@router.get("", response_model=list[ProductRead])
def favorites(user=Depends(current_user), db: Session = Depends(get_db)):
    return FavoriteService(db).list(user.id)


@router.put("/{product_id}", status_code=204)
def add_favorite(product_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
    FavoriteService(db).add(user.id, product_id)


@router.delete("/{product_id}", status_code=204)
def remove_favorite(product_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
    FavoriteService(db).remove(user.id, product_id)
