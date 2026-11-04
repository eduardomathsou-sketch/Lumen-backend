from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.api.deps import cart_session, get_db
from app.schemas.order import CheckoutWrite
from app.services import order_service
from app.utils.pagination import Page, order_page_params

router = APIRouter(prefix="/orders", tags=["checkout"])


@router.post("", status_code=201)
def create_order(body: CheckoutWrite, idempotency_key: str = Header(min_length=8, max_length=100),
                 cart=Depends(cart_session), db: Session = Depends(get_db)):
    return order_service.create_order(db, cart, body, idempotency_key)


@router.get("")
def list_orders(page: Page = Depends(order_page_params), cart=Depends(cart_session), db: Session = Depends(get_db)):
    return order_service.list_orders(db, cart, page)


@router.get("/{order_id}")
def get_order(order_id: str, cart=Depends(cart_session), db: Session = Depends(get_db)):
    return order_service.order_read(db, order_service.find_order(db, cart, order_id))


@router.post("/{order_id}/pix")
def pay_order(order_id: str, cart=Depends(cart_session), db: Session = Depends(get_db)):
    return order_service.pay_order(db, cart, order_service.find_order(db, cart, order_id))


@router.post("/{order_id}/refresh")
def refresh_order(order_id: str, cart=Depends(cart_session), db: Session = Depends(get_db)):
    return order_service.refresh_order(db, cart, order_service.find_order(db, cart, order_id))


@router.post("/{order_id}/cancel")
def cancel_order(order_id: str, cart=Depends(cart_session), db: Session = Depends(get_db)):
    return order_service.refresh_order(db, cart, order_service.find_order(db, cart, order_id), cancel=True)
