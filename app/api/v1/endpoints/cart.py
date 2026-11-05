from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import cart_session, client_ip, get_db
from app.core.config import get_settings
from app.schemas.cart import CartItemWrite
from app.services import auth_service, cart_service

router = APIRouter(prefix="/cart", tags=["checkout"])


@router.post("", status_code=201)
def new_cart(request: Request, db: Session = Depends(get_db)):
    # Sem limite, um script criaria sacolas sem parar só para encher o banco.
    auth_service.throttle(db, f"cart:{client_ip(request)}", get_settings().CART_IP_LIMIT)
    return cart_service.new_cart(db)


@router.get("")
def get_cart(cart=Depends(cart_session), db: Session = Depends(get_db)):
    return cart_service.cart_read(db, cart)


@router.put("/items/{product_id}")
def change_item(product_id: int, body: CartItemWrite, cart=Depends(cart_session), db: Session = Depends(get_db)):
    return cart_service.change_item(db, cart, product_id, body.quantity, body.version, body.variant_id)


@router.get("/quote")
def get_quote(postal_code: str | None = Query(default=None, pattern=r'^\d{8}$'),
              coupon: str | None = Query(default=None, pattern=r'^[A-Za-z0-9_-]{3,30}$'),
              cart=Depends(cart_session), db: Session = Depends(get_db)):
    return cart_service.quote(db, cart, postal_code, coupon)
