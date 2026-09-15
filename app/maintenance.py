"""Run every minute with the same environment as the API: python -m app.maintenance."""
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models.cart import Cart
from app.models.order import Order
from app.services.commerce_service import refresh_order


def run():
    with SessionLocal() as db:
        ids = list(db.scalars(select(Order.id).where(Order.status == "awaiting_payment")))
    failed = 0
    for order_id in ids:
        with SessionLocal() as db:
            try:
                order = db.get(Order, order_id)
                refresh_order(db, db.get(Cart, order.cart_id), order)
            except Exception:
                db.rollback()
                failed += 1
                # No credentials, address, CPF or provider response in logs.
                print(f"Pedido {order_id}: conciliação pendente; será repetida na próxima execução.")
    print(f"Pedidos verificados: {len(ids)}; pendências: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(run())
