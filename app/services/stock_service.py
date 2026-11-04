"""Reserva e devolução de estoque.

Reserva acontece ao criar o pedido; devolução só quando a cobrança não pode mais ser paga
(recusada, cancelada ou vencida e cancelada no provedor). Sempre em ordem de id de produto,
para duas compras simultâneas nunca travarem uma à outra (deadlock).
"""
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict
from app.models.cart import Cart
from app.models.order import Order
from app.repositories.product_repository import ProductRepository, VariantRepository


def _order(line: dict) -> tuple[int, int]:
    return line["product_id"], line.get("variant_id") or 0


def reserve(db: Session, lines: list[dict]) -> None:
    products, variants = ProductRepository(db), VariantRepository(db)
    for line in sorted(lines, key=_order):
        if line["unit_price_cents"] <= 0:
            raise Conflict("Produto sem preço disponível.")
        if line.get("variant_id"):
            # Com variação, o estoque sai da variação; o produto precisa continuar ativo.
            product = products.get(line["product_id"])
            ok = bool(product and product.is_active) and variants.reserve(line["variant_id"], line["quantity"])
        else:
            ok = products.reserve(line["product_id"], line["quantity"])
        if not ok:
            raise Conflict(f"Estoque insuficiente para {line['name']}.")


def release(db: Session, order: Order, cart: Cart) -> None:
    """Devolve o estoque do pedido uma única vez e libera a sacola."""
    if not order.stock_released:
        products, variants = ProductRepository(db), VariantRepository(db)
        for line in sorted(order.items, key=_order):
            if line.get("variant_id"):
                variants.release(line["variant_id"], line["quantity"])
            else:
                products.release(line["product_id"], line["quantity"])
        order.stock_released = True
    if cart.active_order_id == order.id:
        cart.active_order_id = None
        cart.version += 1
