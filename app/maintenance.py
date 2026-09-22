"""Bounded maintenance, callable by Vercel Cron or python -m app.maintenance."""
import time
from datetime import timedelta
from sqlalchemy import or_, select, update
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.cart import Cart
from app.models.order import Order
from app.models.payment import utc_now
from app.services.commerce_service import refresh_order


def run_batch(session_factory=SessionLocal, *, limit=None, budget_seconds=20):
    start = time.monotonic()
    cutoff = utc_now() - timedelta(seconds=60)
    eligible = or_(Order.maintenance_checked_at.is_(None), Order.maintenance_checked_at < cutoff)
    with session_factory() as db:
        ids = list(db.scalars(select(Order.id).where(
            Order.status == "awaiting_payment", eligible,
        ).order_by(Order.maintenance_checked_at.asc().nullsfirst(), Order.created_at, Order.id)
            .limit(limit or get_settings().MAINTENANCE_MAX_ORDERS)))
    checked = failed = 0
    for order_id in ids:
        # Leave headroom for provider calls and DB cleanup within Vercel's limit.
        if time.monotonic() - start >= budget_seconds:
            break
        with session_factory() as db:
            claimed = db.execute(update(Order).where(
                Order.id == order_id, Order.status == "awaiting_payment", eligible,
            ).values(maintenance_checked_at=utc_now())).rowcount
            db.commit()
            if not claimed:
                continue
            checked += 1
            try:
                order = db.get(Order, order_id)
                refresh_order(db, db.get(Cart, order.cart_id), order)
            except Exception:
                db.rollback()
                failed += 1
                # No credentials, address, CPF or provider response in logs.
                print(f"Pedido {order_id}: conciliação pendente; será repetida na próxima execução.")
    return {"checked": checked, "failed": failed}


def run():
    result = run_batch()
    print(f"Pedidos verificados: {result['checked']}; pendências: {result['failed']}")
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(run())
