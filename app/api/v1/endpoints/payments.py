import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.schemas.payment import ChargeCreate, PaymentRead, ProviderWebhook, ReconciliationResult, WebhookResult
from app.services.payment_service import (
    InvalidWebhookError,
    MercadoPagoProvider,
    PaymentConflictError,
    PaymentProviderConfigurationError,
    PaymentProviderError,
    PaymentProviderRequestError,
    PaymentService,
)

router = APIRouter(prefix="/payments", tags=["payments"])


def to_payment_read(payment) -> PaymentRead:
    return PaymentRead(
        id=payment.id,
        order_reference=payment.order_reference,
        amount=payment.amount,
        currency=payment.currency,
        method=payment.method,
        status=payment.status,
        provider=payment.provider,
        provider_charge_id=payment.provider_charge_id,
        next_action=payment.provider_data or None,
        paid_at=payment.paid_at,
        created_at=payment.created_at,
    )


@router.post("/charges", response_model=PaymentRead, status_code=status.HTTP_201_CREATED)
def create_charge(
    charge: ChargeCreate,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=255),
    db: Session = Depends(get_db),
):
    try:
        payment, replay = PaymentService(db).create_charge(charge, idempotency_key)
    except PaymentConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PaymentProviderConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except PaymentProviderRequestError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except PaymentProviderError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if replay:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotency-Replayed"] = "true"
    return to_payment_read(payment)


@router.get("/charges/{provider_charge_id}", response_model=PaymentRead)
def get_charge(provider_charge_id: str, db: Session = Depends(get_db)):
    payment = PaymentService(db).get_charge(provider_charge_id)
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment charge was not found")
    return to_payment_read(payment)


@router.post("/webhooks/provider", response_model=WebhookResult)
async def receive_provider_webhook(
    request: Request,
    x_payment_signature: str | None = Header(default=None, alias="X-Payment-Signature"),
    db: Session = Depends(get_db),
):
    raw_body = await request.body()
    service = PaymentService(db)
    try:
        service.verify_webhook_signature(raw_body, x_payment_signature, get_settings().PAYMENT_WEBHOOK_SECRET)
        event = ProviderWebhook.model_validate(json.loads(raw_body))
        payment, duplicate = service.process_webhook(event)
    except (InvalidWebhookError, json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return WebhookResult(status="duplicate" if duplicate else "processed", payment=to_payment_read(payment))


@router.post("/webhooks/mercadopago", response_model=WebhookResult)
async def receive_mercado_pago_webhook(
    request: Request,
    data_id: str = Query(..., alias="data.id", min_length=1),
    x_signature: str | None = Header(default=None, alias="X-Signature"),
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    db: Session = Depends(get_db),
):
    raw_body = await request.body()
    settings = get_settings()
    try:
        MercadoPagoProvider.verify_webhook_signature(
            x_signature, x_request_id, data_id, settings.MERCADO_PAGO_WEBHOOK_SECRET
        )
        notification = json.loads(raw_body)
        if notification.get("type") != "payment":
            raise InvalidWebhookError("Unsupported Mercado Pago webhook topic")
        service = PaymentService(db)
        if not isinstance(service.provider, MercadoPagoProvider):
            raise InvalidWebhookError("Mercado Pago provider is not enabled")
        provider_status = service.provider.get_payment_status(data_id)
        payment, duplicate = service.process_webhook(
            ProviderWebhook.model_validate(
                {
                    "id": f"mercadopago:{notification.get('id', data_id)}",
                    "type": notification.get("action", "payment.updated"),
                    "data": {"provider_charge_id": data_id, "status": provider_status},
                }
            )
        )
    except PaymentProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except (InvalidWebhookError, json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return WebhookResult(status="duplicate" if duplicate else "processed", payment=to_payment_read(payment))


@router.post("/reconcile", response_model=ReconciliationResult)
def reconcile_payments(db: Session = Depends(get_db)):
    try:
        return PaymentService(db).reconcile()
    except PaymentProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
