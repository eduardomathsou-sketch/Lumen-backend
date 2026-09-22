"""Guest checkout. Prices and inventory are authoritative on the server."""
import hashlib
import json
import secrets
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.cart import Cart
from app.models.account import AccountCart
from app.models.category import Category  # noqa: F401 - register Product.category for the worker
from app.models.order import Order
from app.models.payment import Payment, utc_now, as_utc
from app.models.product import Product
from app.schemas.order import CheckoutWrite
from app.schemas.payment import ChargeCreate
from app.services.payment_service import PaymentService, default_payment_provider, MercadoPagoProvider, SandboxPaymentProvider


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def cents(value) -> int:
    return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def new_cart(db: Session):
    token = secrets.token_urlsafe(32)
    cart = Cart(token_hash=digest(token), items=[])
    db.add(cart)
    db.commit()
    return {"token": token, "cart": cart_read(db, cart)}


def find_cart(db: Session, token: str | None) -> Cart:
    cart = db.scalar(select(Cart).where(Cart.token_hash == digest(token or "")))
    if cart:
        lock_cart(db, cart)
    if not cart or db.scalar(select(AccountCart).where(AccountCart.cart_id == cart.id)):
        raise HTTPException(401, "Sua sessão de compra não foi encontrada.")
    return cart


def lock_cart(db: Session, cart: Cart):
    # Acquires a write lock on SQLite and a row lock on PostgreSQL.
    db.execute(update(Cart).where(Cart.id == cart.id).values(version=Cart.version))
    db.refresh(cart)


def cart_read(db: Session, cart: Cart):
    items = []
    for line in cart.items:
        product = db.get(Product, line["product_id"])
        available = product is not None and product.is_active
        items.append({
            "product_id": line["product_id"], "name": product.name if product else "Produto indisponível",
            "quantity": line["quantity"], "unit_price_cents": cents(product.price) if product else 0,
            "stock": product.stock if available else 0, "available": available,
        })
    return {"version": cart.version, "items": items, "active_order_id": cart.active_order_id,
            "subtotal_cents": sum(x["unit_price_cents"] * x["quantity"] for x in items)}


def change_item(db: Session, cart: Cart, product_id: int, quantity: int, version: int):
    lock_cart(db, cart)
    if cart.active_order_id:
        raise HTTPException(409, "Retome ou cancele o pedido pendente antes de alterar a sacola.")
    if version != cart.version:
        raise HTTPException(409, "A sacola mudou. Atualize e tente novamente.")
    product = db.get(Product, product_id)
    if quantity and (not product or not product.is_active or product.stock < quantity):
        raise HTTPException(409, "Produto indisponível ou quantidade maior que o estoque.")
    lines = [line for line in cart.items if line["product_id"] != product_id]
    if quantity:
        if len(lines) >= 50:
            raise HTTPException(422, "Limite de 50 produtos por sacola.")
        lines.append({"product_id": product_id, "quantity": quantity})
    cart.items = lines
    cart.version += 1
    db.commit()
    return cart_read(db, cart)


def quote(db: Session, cart: Cart):
    settings = get_settings()
    shipping = settings.SHIPPING_FLAT_RATE_CENTS
    if shipping is None or shipping < 0:
        raise HTTPException(503, "A entrega ainda não foi configurada pela loja.")
    result = cart_read(db, cart)
    result.update(shipping_cents=shipping, shipping_label=settings.SHIPPING_LABEL,
                  shipping_days=settings.SHIPPING_DAYS,
                  total_cents=result["subtotal_cents"] + shipping)
    return result


def find_order(db: Session, cart: Cart, order_id: str) -> Order:
    order = db.scalar(select(Order).where(Order.id == order_id, Order.cart_id == cart.id))
    if not order:
        raise HTTPException(404, "Pedido não encontrado.")
    return order


def create_order(db: Session, cart: Cart, request: CheckoutWrite, key: str):
    lock_cart(db, cart)
    checkout_key = digest(f"{cart.id}:{key}")
    fingerprint = digest(json.dumps(request.model_dump(), sort_keys=True))
    prior = db.scalar(select(Order).where(Order.checkout_key == checkout_key))
    if prior:
        if prior.request_hash != fingerprint:
            raise HTTPException(409, "Esta tentativa já foi usada para outro checkout.")
        return order_read(db, prior)
    if cart.active_order_id:
        raise HTTPException(409, "Você já tem um pedido pendente. Retome o pagamento pela sacola.")
    summary = quote(db, cart)
    if not summary["items"]:
        raise HTTPException(422, "Sua sacola está vazia.")
    if cart.version != request.cart_version or summary["total_cents"] != request.expected_total_cents:
        raise HTTPException(409, "Os valores mudaram. Revise a sacola antes de confirmar.")
    for line in sorted(summary["items"], key=lambda x: x["product_id"]):
        if line["unit_price_cents"] <= 0:
            raise HTTPException(409, "Produto sem preço disponível.")
        result = db.execute(update(Product).where(
            Product.id == line["product_id"], Product.is_active.is_(True), Product.stock >= line["quantity"]
        ).values(stock=Product.stock - line["quantity"]))
        if result.rowcount != 1:
            raise HTTPException(409, f"Estoque insuficiente para {line['name']}.")
    settings = get_settings()
    order = Order(
        id=str(uuid.uuid4()), cart_id=cart.id, checkout_key=checkout_key, request_hash=fingerprint,
        items=summary["items"], address=request.address.model_dump(), payer_email=request.payer_email,
        payer_document=request.payer_document, subtotal_cents=summary["subtotal_cents"],
        shipping_cents=summary["shipping_cents"], total_cents=summary["total_cents"],
        shipping_label=summary["shipping_label"], shipping_days=summary["shipping_days"],
        provider=settings.PAYMENT_PROVIDER.lower(),
        expires_at=utc_now() + timedelta(minutes=settings.ORDER_TTL_MINUTES),
    )
    db.add(order)
    cart.active_order_id = order.id
    cart.version += 1
    db.commit()
    return order_read(db, order)


def order_read(db: Session, order: Order):
    payment = db.scalar(select(Payment).where(Payment.order_reference == order.id))
    payment_data = None
    if payment:
        payment_data = {"provider_charge_id": payment.provider_charge_id, "status": payment.status,
                        "provider": payment.provider, "next_action": payment.provider_data}
    return {"id": order.id, "status": order.status, "items": order.items,
            "address": order.address, "payer_email": order.payer_email,
            "subtotal_cents": order.subtotal_cents, "shipping_cents": order.shipping_cents,
            "total_cents": order.total_cents, "shipping_label": order.shipping_label,
            "shipping_days": order.shipping_days, "created_at": order.created_at,
            "expires_at": order.expires_at, "payment": payment_data}


def sync_order(db: Session, payment: Payment):
    order = db.scalar(select(Order).where(Order.id == payment.order_reference))
    if not order:
        return
    cart = db.get(Cart, order.cart_id)
    lock_cart(db, cart)
    db.refresh(order)
    if payment.status == "paid":
        # A late approval after a confirmed cancellation requires operator handling.
        order.status = "review_required" if order.stock_released else "paid"
        if cart.active_order_id == order.id:
            cart.items = []
            cart.active_order_id = None
            cart.version += 1
    elif payment.status in {"failed", "cancelled"} and order.status not in {"paid", "refunded"}:
        release_stock(db, order, cart)
        order.status = payment.status
    elif payment.status == "refunded":
        order.status = "refunded"
    db.flush()


def release_stock(db: Session, order: Order, cart: Cart):
    if not order.stock_released:
        for line in sorted(order.items, key=lambda x: x["product_id"]):
            db.execute(update(Product).where(Product.id == line["product_id"])
                       .values(stock=Product.stock + line["quantity"]))
        order.stock_released = True
    if cart.active_order_id == order.id:
        cart.active_order_id = None
        cart.version += 1


def pay_order(db: Session, cart: Cart, order: Order):
    lock_cart(db, cart)
    db.refresh(order)
    if order.status != "awaiting_payment":
        return order_read(db, order)
    existing = db.scalar(select(Payment).where(Payment.order_reference == order.id))
    if existing:
        return order_read(db, order)
    provider = default_payment_provider(order.provider)
    if provider.name != order.provider:
        raise HTTPException(409, "O provedor deste pedido mudou. Entre em contato com a loja.")
    charge = ChargeCreate(order_reference=order.id, amount=Decimal(order.total_cents) / 100,
                          method="pix", payer_email=order.payer_email, payer_document=order.payer_document)
    PaymentService(db, provider).create_charge(charge, f"order-{order.id}", commit=False)
    db.commit()
    return order_read(db, order)


def refresh_order(db: Session, cart: Cart, order: Order, cancel=False):
    lock_cart(db, cart)
    db.refresh(order)
    if order.status != "awaiting_payment":
        return order_read(db, order)
    expired = as_utc(order.expires_at) <= utc_now()
    # Even after a timeout we replay the stable provider key before cancellation:
    # never release inventory while an unknown payment may still be payable.
    pay_order(db, cart, order)
    lock_cart(db, cart)
    payment = db.scalar(select(Payment).where(Payment.order_reference == order.id))
    service = PaymentService(db, default_payment_provider(order.provider))
    if service.provider.name != order.provider:
        raise HTTPException(409, "Provedor do pedido indisponível.")
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
