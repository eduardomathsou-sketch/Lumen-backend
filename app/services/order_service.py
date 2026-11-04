"""Regras do pedido: criação idempotente, PIX, consulta, cancelamento e sincronização com o pagamento."""
import json
import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import Conflict, NotFound, Unprocessable
from app.core.security import digest
from app.models.cart import Cart
from app.models.order import Order
from app.models.payment import Payment, as_utc, utc_now
from app.repositories.cart_repository import CartRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.payment_repository import PaymentRepository
from app.schemas.order import CheckoutWrite
from app.schemas.payment import ChargeCreate
from app.models.user import User
from app.schemas.order import FulfillmentWrite
from app.services import cart_service, coupon_service, shipping_service, stock_service, user_service
from app.services.payment_service import MercadoPagoProvider, PaymentService, default_payment_provider
from app.utils.pagination import Page


def order_read(db: Session, order: Order) -> dict:
    payment = PaymentRepository(db).by_order(order.id)
    payment_data = None
    if payment:
        payment_data = {"provider_charge_id": payment.provider_charge_id, "status": payment.status,
                        "provider": payment.provider, "next_action": payment.provider_data}
    return {"id": order.id, "status": order.status, "items": order.items,
            "address": order.address, "payer_email": order.payer_email,
            "subtotal_cents": order.subtotal_cents, "shipping_cents": order.shipping_cents,
            "total_cents": order.total_cents, "shipping_label": order.shipping_label,
            "shipping_days": order.shipping_days, "created_at": order.created_at,
            "expires_at": order.expires_at, "payment": payment_data,
            "discount_cents": order.discount_cents, "coupon_code": order.coupon_code,
            "fulfillment_status": order.fulfillment_status, "tracking_code": order.tracking_code,
            "shipped_at": order.shipped_at, "delivered_at": order.delivered_at}


def find_order(db: Session, cart: Cart, order_id: str) -> Order:
    order = OrderRepository(db).get_for_cart(order_id, cart.id)
    if not order:
        raise NotFound("Pedido não encontrado.")
    return order


def list_orders(db: Session, cart: Cart, page: Page) -> list[dict]:
    return [order_read(db, order) for order in OrderRepository(db).list_for_cart(cart.id, page)]


def create_order(db: Session, cart: Cart, request: CheckoutWrite, key: str, user: User | None = None) -> dict:
    """1) trava a sacola 2) idempotência 3) recalcula e compara 4) reserva estoque 5) cria o pedido."""
    orders = OrderRepository(db)
    cart_service.lock(db, cart)
    checkout_key = digest(f"{cart.id}:{key}")
    fingerprint = digest(json.dumps(request.model_dump(), sort_keys=True))
    prior = orders.get_by_checkout_key(checkout_key)
    if prior:
        if prior.request_hash != fingerprint:
            raise Conflict("Esta tentativa já foi usada para outro checkout.")
        return order_read(db, prior)
    if cart.active_order_id:
        raise Conflict("Você já tem um pedido pendente. Retome o pagamento pela sacola.")
    summary = cart_service.quote(db, cart, coupon_code=request.coupon_code)
    address = (request.address.model_dump() if request.address is not None
               else user_service.saved_address_snapshot(db, user, request.address_id))
    shipping_details = None
    if get_settings().shipping_mode == 'melhorenvio':
        selected, shipping_details = shipping_service.select_rate(db, cart, summary, request, address['postal_code'])
        summary.update(shipping_cents=selected['price_cents'], shipping_label=selected['label'],
                       shipping_days=selected['days'],
                       total_cents=summary['subtotal_cents'] - summary['discount_cents'] + selected['price_cents'])
    if not summary["items"]:
        raise Unprocessable("Sua sacola está vazia.")
    if not all(item["available"] for item in summary["items"]):
        raise Conflict("Há produtos indisponíveis na sacola. Revise antes de confirmar.")
    if cart.version != request.cart_version or summary["total_cents"] != request.expected_total_cents:
        raise Conflict("Os valores mudaram. Revise a sacola antes de confirmar.")
    stock_service.reserve(db, summary["items"])
    if summary["coupon_code"]:
        coupon_service.reserve_use(db, summary["coupon_code"])
    settings = get_settings()
    order = orders.add(Order(
        id=str(uuid.uuid4()), cart_id=cart.id, checkout_key=checkout_key, request_hash=fingerprint,
        items=summary["items"], address=address, payer_email=request.payer_email,
        payer_document=request.payer_document, subtotal_cents=summary["subtotal_cents"],
        shipping_cents=summary["shipping_cents"], total_cents=summary["total_cents"],
        shipping_label=summary["shipping_label"], shipping_days=summary["shipping_days"],
        shipping_details=shipping_details,
        discount_cents=summary["discount_cents"], coupon_code=summary["coupon_code"],
        provider=settings.PAYMENT_PROVIDER.lower(),
        expires_at=utc_now() + timedelta(minutes=settings.ORDER_TTL_MINUTES),
    ))
    cart.active_order_id = order.id
    cart.version += 1
    db.commit()
    return order_read(db, order)


def sync_order(db: Session, payment: Payment) -> None:
    """Leva o status do pagamento para o pedido (chamado sempre que o pagamento muda)."""
    order = OrderRepository(db).get(payment.order_reference)
    if not order:
        return
    cart = CartRepository(db).get(order.cart_id)
    cart_service.lock(db, cart)
    db.refresh(order)
    if payment.status == "paid":
        # Aprovação depois de o estoque já ter voltado: a loja decide manualmente.
        order.status = "review_required" if order.stock_released else "paid"
        if order.status == "paid" and order.fulfillment_status is None:
            order.fulfillment_status = "preparing"
        if cart.active_order_id == order.id:
            cart.items = []
            cart.active_order_id = None
            cart.version += 1
    elif payment.status in {"failed", "cancelled"} and order.status not in {"paid", "refunded"}:
        if order.coupon_code and not order.stock_released:
            coupon_service.release_use(db, order.coupon_code)  # devolve o uso do cupom junto com o estoque
        stock_service.release(db, order, cart)
        order.status = payment.status
    elif payment.status == "refunded":
        order.status = "refunded"
    db.flush()


def pay_order(db: Session, cart: Cart, order: Order) -> dict:
    """Gera (ou retoma) o PIX usando só o total congelado no pedido."""
    cart_service.lock(db, cart)
    db.refresh(order)
    if order.status != "awaiting_payment" or PaymentRepository(db).by_order(order.id):
        return order_read(db, order)
    provider = default_payment_provider(order.provider)
    if provider.name != order.provider:
        raise Conflict("O provedor deste pedido mudou. Entre em contato com a loja.")
    charge = ChargeCreate(order_reference=order.id, amount=Decimal(order.total_cents) / 100,
                          method="pix", payer_email=order.payer_email, payer_document=order.payer_document)
    # Chave estável por pedido: repetir depois de um timeout devolve a mesma cobrança.
    PaymentService(db, provider).create_charge(charge, f"order-{order.id}", commit=False)
    db.commit()
    return order_read(db, order)


def refresh_order(db: Session, cart: Cart, order: Order, cancel: bool = False) -> dict:
    cart_service.lock(db, cart)
    db.refresh(order)
    if order.status != "awaiting_payment":
        return order_read(db, order)
    expired = as_utc(order.expires_at) <= utc_now()
    # Mesmo depois do prazo, repete a chave estável antes de cancelar:
    # nunca devolvemos estoque enquanto uma cobrança desconhecida ainda puder ser paga.
    pay_order(db, cart, order)
    cart_service.lock(db, cart)
    payment = PaymentRepository(db).by_order(order.id)
    service = PaymentService(db, default_payment_provider(order.provider))
    if service.provider.name != order.provider:
        raise Conflict("Provedor do pedido indisponível.")
    if isinstance(service.provider, MercadoPagoProvider):
        service.refresh_payment(payment)
        if (cancel or expired) and payment.status == "pending":
            service.provider.cancel_charge(payment.provider_charge_id)
            service.refresh_payment(payment)
    elif cancel or expired:
        service._apply_status(payment, "cancelled")
    sync_order(db, payment)
    db.commit()
    return order_read(db, order)


# --- Administração de pedidos e entrega ---
FULFILLMENT_NEXT = {"preparing": "shipped", "shipped": "delivered"}


def mask_document(document: str) -> str:
    # O painel só precisa conferir o final do CPF/CNPJ (minimização de dados, LGPD).
    return "*" * (len(document) - 2) + document[-2:]


def admin_summary(order: Order) -> dict:
    return {"id": order.id, "created_at": order.created_at, "status": order.status,
            "fulfillment_status": order.fulfillment_status, "total_cents": order.total_cents,
            "payer_email": order.payer_email, "units": sum(i["quantity"] for i in order.items),
            "recipient": order.address.get("recipient")}


def admin_list(db: Session, page: Page, status: str | None = None, fulfillment: str | None = None) -> list[dict]:
    return [admin_summary(o) for o in OrderRepository(db).search(page, status, fulfillment)]


def _admin_order(db: Session, order_id: str) -> Order:
    order = OrderRepository(db).get(order_id)
    if order is None:
        raise NotFound("Pedido não encontrado.")
    return order


def admin_get(db: Session, order_id: str) -> dict:
    order = _admin_order(db, order_id)
    return {**order_read(db, order), "payer_document": mask_document(order.payer_document),
            "shipping_details": order.shipping_details}


def advance_fulfillment(db: Session, order_id: str, body: FulfillmentWrite) -> dict:
    order = _admin_order(db, order_id)
    cart_service.lock(db, CartRepository(db).get(order.cart_id))  # serializa com o pagamento
    db.refresh(order)
    if order.status != "paid":
        raise Conflict("Só pedidos pagos seguem para entrega.")
    if FULFILLMENT_NEXT.get(order.fulfillment_status) != body.status:
        raise Conflict(f"O pedido está em '{order.fulfillment_status}' e não pode ir para '{body.status}'.")
    order.fulfillment_status = body.status
    if body.status == "shipped":
        order.tracking_code = body.tracking_code or None
        order.shipped_at = utc_now()
    else:
        order.delivered_at = utc_now()
    db.commit()
    return admin_get(db, order.id)
