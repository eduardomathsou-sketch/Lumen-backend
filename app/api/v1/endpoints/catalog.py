from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models.category import Category
from app.models.product import Product
from app.models.account import Favorite
from app.services.auth_service import current_user
from app.api.v1.endpoints.products import get_product_by_id

router = APIRouter(tags=["catalog"])


@router.get("/categories")
def categories(db: Session = Depends(get_db)):
    return [{"id": c.id, "name": c.name, "description": c.description}
            for c in db.scalars(select(Category).order_by(Category.name))]


@router.get("/favorites")
def favorites(user=Depends(current_user), db: Session = Depends(get_db)):
    ids = db.scalars(select(Favorite.product_id).join(Product).where(
        Favorite.user_id == user.id, Product.is_active.is_(True)).order_by(Favorite.product_id)).all()
    return [get_product_by_id(product_id, db) for product_id in ids]


@router.put("/favorites/{product_id}", status_code=204)
def add_favorite(product_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product or not product.is_active:
        raise HTTPException(404, "Produto não encontrado.")
    if not db.get(Favorite, (user.id, product_id)):
        db.add(Favorite(user_id=user.id, product_id=product_id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()


@router.delete("/favorites/{product_id}", status_code=204)
def remove_favorite(product_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(Favorite).where(Favorite.user_id == user.id, Favorite.product_id == product_id))
    db.commit()
