import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.models.payment import Payment
from app.schemas.payment import ProviderWebhook
from app.services.payment_service import InvalidWebhookError, MercadoPagoProvider, PaymentService, default_payment_provider
from app.services.mercado_pago_orders import ORDER_ID
from app.services.commerce_service import lock_cart
from app.models.cart import Cart
from app.models.order import Order

router = APIRouter(prefix="/payments", tags=["payments"])


def require_admin(authorization: str | None = Header(default=None)):
    token = get_settings().PAYMENT_ADMIN_TOKEN
    if not token or not hmac.compare_digest((authorization or "").encode(), f"Bearer {token}".encode()):
        raise HTTPException(401, "Acesso administrativo necessário.")


@router.post("/charges", deprecated=True)
def retired_charge():
    raise HTTPException(410, "Crie um pedido e use POST /orders/{order_id}/pix.")


@router.get("/charges/{charge_id}", deprecated=True)
def retired_get(charge_id: str):
    raise HTTPException(410, "Consulte o pedido autenticado em /orders/{order_id}.")


def lock_payment(db, charge_id):
    payment = db.scalar(select(Payment).where(Payment.provider_charge_id == charge_id))
    if not payment:
        raise HTTPException(503, "Pagamento ainda não disponível. Tente novamente.")
    order = db.get(Order, payment.order_reference)
    if order:
        lock_cart(db, db.get(Cart, order.cart_id))
        db.refresh(payment)
    return payment


@router.post("/webhooks/provider")
async def sandbox_webhook(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    if settings.PAYMENT_PROVIDER != "sandbox" or not settings.PAYMENT_WEBHOOK_SECRET:
        raise HTTPException(404, "Webhook indisponível.")
    raw = await request.body()
    service = PaymentService(db)
    try:
        service.verify_webhook_signature(raw, request.headers.get("x-payment-signature"), settings.PAYMENT_WEBHOOK_SECRET)
        event = ProviderWebhook.model_validate_json(raw)
        payment = lock_payment(db, event.data.provider_charge_id)
        if payment.provider != "sandbox":
            raise InvalidWebhookError("Provedor inválido")
        _, duplicate = service.process_webhook(event)
    except (InvalidWebhookError, ValidationError) as exc:
        raise HTTPException(400, "Notificação inválida.") from exc
    return {"status": "duplicate" if duplicate else "processed"}


@router.post("/webhooks/mercadopago")
async def mercado_pago_webhook(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    if settings.PAYMENT_PROVIDER not in {"mercadopago", "mercadopago_orders"}:
        raise HTTPException(404, "Webhook indisponível.")
    data_id = request.query_params.get("data.id", "")
    signature = request.headers.get("x-signature")
    try:
        is_order = bool(ORDER_ID.fullmatch(data_id))
        if not is_order and (not data_id.isascii() or not data_id.isdigit() or len(data_id) > 40):
            raise InvalidWebhookError("Identificador inválido")
        MercadoPagoProvider.verify_webhook_signature(signature, request.headers.get("x-request-id"),
                                                     data_id, settings.MERCADO_PAGO_WEBHOOK_SECRET)
        notification = json.loads(await request.body())
        if not isinstance(notification, dict) or notification.get("type") != ("order" if is_order else "payment"):
            raise InvalidWebhookError("Tópico inválido")
        if str((notification.get("data") or {}).get("id")) != data_id:
            raise InvalidWebhookError("Identificador divergente")
    except (InvalidWebhookError, ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(401, "Assinatura ou notificação inválida.") from exc
    payment = lock_payment(db, data_id)
    expected_provider = "mercadopago_orders" if is_order else "mercadopago"
    if payment.provider != expected_provider:
        raise HTTPException(401, "Provedor da notificação inválido.")
    service = PaymentService(db, default_payment_provider(payment.provider))
    service.refresh_payment(payment)
    event_key = hashlib.sha256(f"{data_id}:{signature}".encode()).hexdigest()
    event = ProviderWebhook(id=f"mp:{event_key}", type="payment.updated",
                            data={"provider_charge_id": data_id, "status": payment.status})
    _, duplicate = service.process_webhook(event)
    db.commit()
    return {"status": "duplicate" if duplicate else "processed"}


@router.post("/reconcile", dependencies=[Depends(require_admin)])
def reconcile(db: Session = Depends(get_db)):
    return PaymentService(db).reconcile()
