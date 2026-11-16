"""Devoluções (Código de Defesa do Consumidor).

- Arrependimento: até 7 dias corridos depois da entrega, sem justificativa (art. 49).
- Defeito: até 90 dias depois da entrega para produto durável (art. 26, II).
A cliente pede pelo app; a loja aprova ou recusa (com motivo) e, quando a peça volta,
registra o reembolso. O reembolso do PIX é feito no painel do Mercado Pago e aqui só
marcamos como feito (e devolvemos as peças ao estoque, se estiverem perfeitas).
"""
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import security_event
from app.core.exceptions import Conflict, NotFound, Unprocessable
from app.models.order import Order
from app.models.payment import as_utc, utc_now
from app.models.return_request import ReturnRequest
from app.repositories.cart_repository import CartRepository
from app.repositories.product_repository import ProductRepository, VariantRepository
from app.services import cart_service, notification_service
from app.utils.pagination import Page

WINDOWS = {"arrependimento": timedelta(days=7), "defeito": timedelta(days=90)}
REASON_LABELS = {"arrependimento": "Arrependimento (7 dias)", "defeito": "Defeito (90 dias)"}


def return_read(item: ReturnRequest) -> dict:
    return {"id": item.id, "order_id": item.order_id, "reason": item.reason, "details": item.details,
            "status": item.status, "admin_note": item.admin_note, "restocked": item.restocked,
            "created_at": item.created_at, "decided_at": item.decided_at, "refunded_at": item.refunded_at}


def return_for_order(db: Session, order_id: str) -> ReturnRequest | None:
    return db.scalar(select(ReturnRequest).where(ReturnRequest.order_id == order_id))


def eligibility(order: Order) -> dict:
    """O que o app mostra no pedido: pode devolver? por qual motivo? até quando?"""
    if order.status != "paid" or order.fulfillment_status != "delivered" or order.delivered_at is None:
        return {"eligible": False, "reasons": {}}
    delivered = as_utc(order.delivered_at)
    now = utc_now()
    reasons = {reason: (delivered + window).isoformat() for reason, window in WINDOWS.items()
               if now <= delivered + window}
    return {"eligible": bool(reasons), "reasons": reasons}


def request_return(db: Session, cart, order: Order, reason: str, details: str) -> dict:
    cart_service.lock(db, cart)  # serializa com outras ações do mesmo pedido
    db.refresh(order)
    if return_for_order(db, order.id):
        raise Conflict("Já existe uma solicitação de devolução para este pedido.")
    if order.status != "paid" or order.fulfillment_status != "delivered":
        raise Conflict("A devolução fica disponível depois que o pedido é entregue.")
    if reason not in eligibility(order)["reasons"]:
        days = WINDOWS[reason].days
        raise Unprocessable(f"O prazo de {days} dias para {REASON_LABELS[reason].split(' (')[0].lower()} terminou.")
    item = ReturnRequest(id=str(uuid.uuid4()), order_id=order.id, reason=reason, details=details,
                         status="requested", restocked=False)
    db.add(item)
    db.flush()
    notification_service.queue_order_email(db, "return_requested", order)
    db.commit()
    return return_read(item)


# --- Administração ---
def admin_list(db: Session, page: Page, status: str | None = None) -> list[dict]:
    statement = select(ReturnRequest).order_by(ReturnRequest.created_at.desc())
    if status:
        statement = statement.where(ReturnRequest.status == status)
    return [return_read(r) for r in db.scalars(statement.offset(page.skip).limit(page.limit))]


def _restock(db: Session, order: Order) -> None:
    products, variants = ProductRepository(db), VariantRepository(db)
    for line in sorted(order.items, key=lambda l: (l["product_id"], l.get("variant_id") or 0)):
        if line.get("variant_id"):
            variants.release(line["variant_id"], line["quantity"])
        else:
            products.release(line["product_id"], line["quantity"])


def admin_decide(db: Session, return_id: str, action: str, note: str, restock: bool) -> dict:
    item = db.get(ReturnRequest, return_id)
    if item is None:
        raise NotFound("Solicitação de devolução não encontrada.")
    order = db.get(Order, item.order_id)
    cart_service.lock(db, CartRepository(db).get(order.cart_id))
    db.refresh(item)
    db.refresh(order)
    allowed = {"approve": "requested", "reject": "requested", "refund": "approved"}
    if item.status != allowed[action]:
        raise Conflict(f"A devolução está em '{item.status}' e não aceita '{action}'.")
    if action == "reject" and not note:
        raise Unprocessable("Explique o motivo da recusa: ele vai para a cliente.")
    now = utc_now()
    item.admin_note = note or item.admin_note
    if action == "approve":
        item.status, item.decided_at = "approved", now
        kind = "return_approved"
    elif action == "reject":
        item.status, item.decided_at = "rejected", now
        kind = "return_rejected"
    else:
        item.status, item.refunded_at = "refunded", now
        order.status = "refunded"
        if restock:
            _restock(db, order)
            item.restocked = True
        kind = "return_refunded"
    ctx = {**notification_service.order_context(order), "note": item.admin_note}
    notification_service.queue(db, kind, order.payer_email, ctx, dedupe_key=f"{kind}:{order.id}")
    db.commit()
    security_event("admin.return", action=action, order=order.id.split("-")[0])
    return return_read(item)
