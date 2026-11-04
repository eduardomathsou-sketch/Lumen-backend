from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import cart_session, get_db
from app.schemas.cart import CartItemWrite
from app.services import cart_service

router = APIRouter(prefix="/cart", tags=["checkout"])


@router.post("", status_code=201)
def new_cart(db: Session = Depends(get_db)):
    return cart_service.new_cart(db)


@router.get("")
def get_cart(cart=Depends(cart_session), db: Session = Depends(get_db)):
    return cart_service.cart_read(db, cart)


@router.put("/items/{product_id}")
def change_item(product_id: int, body: CartItemWrite, cart=Depends(cart_session), db: Session = Depends(get_db)):
    return cart_service.change_item(db, cart, product_id, body.quantity, body.version)


@router.get("/quote")
def get_quote(postal_code: str | None = Query(default=None, pattern=r'^\d{8}$'),
              cart=Depends(cart_session), db: Session = Depends(get_db)):
    return cart_service.quote(db, cart, postal_code)
