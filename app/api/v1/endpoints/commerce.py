from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.order import Order
from app.schemas.cart import CartItemWrite
from app.schemas.order import CheckoutWrite
from app.services import commerce_service as service
from app.services.auth_service import optional_user
from app.models.account import AccountCart
from app.models.cart import Cart
from fastapi import HTTPException

router = APIRouter(tags=["checkout"])


def cart_session(x_cart_token: str | None = Header(default=None), user=Depends(optional_user), db: Session = Depends(get_db)):
    if user:
        link = db.get(AccountCart, user.id)
        if not link:
            raise HTTPException(409, "Entre novamente para recuperar sua sacola.")
        return db.get(Cart, link.cart_id)
    return service.find_cart(db, x_cart_token)


@router.post("/cart", status_code=201)
def new_cart(db: Session = Depends(get_db)):
    return service.new_cart(db)


@router.get("/cart")
def get_cart(cart=Depends(cart_session), db: Session = Depends(get_db)):
    return service.cart_read(db, cart)


@router.put("/cart/items/{product_id}")
def change_item(product_id: int, body: CartItemWrite, cart=Depends(cart_session), db: Session = Depends(get_db)):
    return service.change_item(db, cart, product_id, body.quantity, body.version)


@router.get("/cart/quote")
def get_quote(cart=Depends(cart_session), db: Session = Depends(get_db)):
    return service.quote(db, cart)


@router.post("/orders", status_code=201)
def create_order(body: CheckoutWrite, idempotency_key: str = Header(min_length=8, max_length=100),
                 cart=Depends(cart_session), db: Session = Depends(get_db)):
    return service.create_order(db, cart, body, idempotency_key)


@router.get("/orders")
def list_orders(cart=Depends(cart_session), db: Session = Depends(get_db),
                skip: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100)):
    orders = db.scalars(select(Order).where(Order.cart_id == cart.id)
                        .order_by(Order.created_at.desc()).offset(skip).limit(limit)).all()
    return [service.order_read(db, order) for order in orders]


@router.get("/orders/{order_id}")
def get_order(order_id: str, cart=Depends(cart_session), db: Session = Depends(get_db)):
    return service.order_read(db, service.find_order(db, cart, order_id))


@router.post("/orders/{order_id}/pix")
def pay_order(order_id: str, cart=Depends(cart_session), db: Session = Depends(get_db)):
    return service.pay_order(db, cart, service.find_order(db, cart, order_id))


@router.post("/orders/{order_id}/refresh")
def refresh_order(order_id: str, cart=Depends(cart_session), db: Session = Depends(get_db)):
    return service.refresh_order(db, cart, service.find_order(db, cart, order_id))


@router.post("/orders/{order_id}/cancel")
def cancel_order(order_id: str, cart=Depends(cart_session), db: Session = Depends(get_db)):
    return service.refresh_order(db, cart, service.find_order(db, cart, order_id), cancel=True)
