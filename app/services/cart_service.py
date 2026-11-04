"""Regras da sacola. Preço e estoque vêm sempre do servidor."""
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import Conflict, ServiceUnavailable, Unauthorized, Unprocessable
from app.core.security import digest, new_token
from app.models.cart import Cart
from app.models.user import User
from app.repositories.cart_repository import CartRepository
from app.repositories.product_repository import ProductRepository
from app.services import shipping_service

MAX_LINES = 50


def new_cart(db: Session) -> dict:
    token = new_token(32)
    cart = CartRepository(db).add(Cart(token_hash=digest(token), items=[]))
    db.commit()
    return {"token": token, "cart": cart_read(db, cart)}


def guest_cart(db: Session, token: str | None) -> Cart:
    """Sacola de visitante pelo token. Depois de vinculada a uma conta, o token sozinho não vale mais."""
    carts = CartRepository(db)
    cart = carts.get_by_token_hash(digest(token or ""))
    if cart:
        carts.lock(cart)
    if not cart or carts.is_linked(cart.id):
        raise Unauthorized("Sua sessão de compra não foi encontrada.")
    return cart


def account_cart(db: Session, user: User) -> Cart:
    carts = CartRepository(db)
    link = carts.link_for_user(user.id)
    if not link:
        raise Conflict("Entre novamente para recuperar sua sacola.")
    return carts.get(link.cart_id)


def lock(db: Session, cart: Cart) -> None:
    CartRepository(db).lock(cart)


def cart_read(db: Session, cart: Cart) -> dict:
    products = ProductRepository(db).get_many(line["product_id"] for line in cart.items)
    items = []
    for line in cart.items:
        product = products.get(line["product_id"])
        available = product is not None and product.is_active
        items.append({
            "product_id": line["product_id"], "name": product.name if product else "Produto indisponível",
            "image_url": product.image_url if product else None,
            "quantity": line["quantity"], "unit_price_cents": product.price_cents if product else 0,
            "stock": product.stock if available else 0, "available": available,
        })
    return {"version": cart.version, "items": items, "active_order_id": cart.active_order_id,
            "subtotal_cents": sum(x["unit_price_cents"] * x["quantity"] for x in items)}


def change_item(db: Session, cart: Cart, product_id: int, quantity: int, version: int) -> dict:
    lock(db, cart)
    if cart.active_order_id:
        raise Conflict("Retome ou cancele o pedido pendente antes de alterar a sacola.")
    if version != cart.version:
        raise Conflict("A sacola mudou. Atualize e tente novamente.")
    product = ProductRepository(db).get(product_id)
    if quantity and (not product or not product.is_active or product.stock < quantity):
        raise Conflict("Produto indisponível ou quantidade maior que o estoque.")
    lines = [line for line in cart.items if line["product_id"] != product_id]
    if quantity:
        if len(lines) >= MAX_LINES:
            raise Unprocessable("Limite de 50 produtos por sacola.")
        lines.append({"product_id": product_id, "quantity": quantity})
    cart.items = lines
    cart.version += 1
    db.commit()
    return cart_read(db, cart)


def quote(db: Session, cart: Cart, postal_code: str | None = None) -> dict:
    settings = get_settings()
    result = cart_read(db, cart)
    if settings.shipping_mode == 'melhorenvio':
        shipping_quote = shipping_service.calculate(db, cart, result, postal_code) if postal_code else None
        result.update(shipping_cents=0, shipping_label='Entrega a calcular', shipping_days=0,
                      total_cents=result['subtotal_cents'], shipping_required=True,
                      shipping_options=shipping_quote.options if shipping_quote else [],
                      shipping_quote_id=shipping_quote.id if shipping_quote else None,
                      postal_code=postal_code,
                      shipping_expires_at=shipping_quote.expires_at if shipping_quote else None)
        return result
    shipping = settings.SHIPPING_FLAT_RATE_CENTS
    if shipping is None or shipping < 0:
        raise ServiceUnavailable("A entrega ainda não foi configurada pela loja.")
    result.update(shipping_cents=shipping, shipping_label=settings.SHIPPING_LABEL,
                  shipping_days=settings.SHIPPING_DAYS,
                  total_cents=result["subtotal_cents"] + shipping)
    return result
