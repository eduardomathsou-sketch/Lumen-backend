"""Rotina de manutenção (a cada minuto): confere pedidos pendentes, cancela os vencidos,
envia a fila de e-mails e apaga o que já venceu.

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
from app.repositories.shipping_repository import ShippingQuoteRepository
from app.repositories.user_repository import AttemptRepository, SessionRepository
from app.services import cart_reminder_service, notification_service, password_service
from app.services.order_service import refresh_order


def cleanup(db) -> dict:
    """Apaga o que já venceu: sessões, contadores de tentativas e cotações de frete."""
    now = utc_now()
    removed = {
        "sessions": SessionRepository(db).delete_expired(now),
        "attempts": AttemptRepository(db).delete_older_than(now - timedelta(hours=1)),
        "quotes": ShippingQuoteRepository(db).delete_all_expired(now),
        "password_resets": password_service.delete_expired(db, now),
        "emails": notification_service.delete_old(db, now),
    }
    db.commit()
    return removed


def run_batch(session_factory=SessionLocal, *, limit=None, budget_seconds=20):
    start = time.monotonic()
    cutoff = utc_now() - timedelta(seconds=60)
    with session_factory() as db:
        cleanup(db)
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
    emails = {"sent": 0, "failed": 0}
    # E-mails depois dos pedidos: conciliar pagamento é mais urgente que avisar.
    if time.monotonic() - start < budget_seconds:
        with session_factory() as db:
            cart_reminder_service.queue_reminders(db)
            emails = notification_service.dispatch_pending(db)
    # Falha de e-mail não vira 503: ele já está agendado para nova tentativa.
    return {"checked": checked, "failed": failed, "emails_sent": emails["sent"], "emails_retry": emails["failed"]}


def run():
    result = run_batch()
    print(f"Pedidos verificados: {result['checked']}; pendências: {result['failed']}")
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(run())
