"""Rotina de manutenção (a cada minuto): confere pedidos pendentes e cancela os vencidos.

Chamada pelo agendador externo em GET /api/internal/maintenance ou por
`python -m app.maintenance`.
"""
import time
from datetime import timedelta

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.payment import utc_now
from app.repositories.cart_repository import CartRepository
from app.repositories.order_repository import OrderRepository
from app.services.order_service import refresh_order


def run_batch(session_factory=SessionLocal, *, limit=None, budget_seconds=20):
    start = time.monotonic()
    cutoff = utc_now() - timedelta(seconds=60)
    with session_factory() as db:
        ids = OrderRepository(db).pending_for_maintenance(cutoff, limit or get_settings().MAINTENANCE_MAX_ORDERS)
    checked = failed = 0
    for order_id in ids:
        # Deixa folga para chamadas ao provedor dentro do limite de tempo da Vercel.
        if time.monotonic() - start >= budget_seconds:
            break
        with session_factory() as db:
            orders = OrderRepository(db)
            claimed = orders.claim_for_maintenance(order_id, cutoff, utc_now())
            db.commit()
            if not claimed:
                continue
            checked += 1
            try:
                order = orders.get(order_id)
                refresh_order(db, CartRepository(db).get(order.cart_id), order)
            except Exception:
                db.rollback()
                failed += 1
                # Sem credenciais, endereço, CPF ou resposta do provedor no log.
                print(f"Pedido {order_id}: conciliação pendente; será repetida na próxima execução.")
    return {"checked": checked, "failed": failed}


def run():
    result = run_batch()
    print(f"Pedidos verificados: {result['checked']}; pendências: {result['failed']}")
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(run())
