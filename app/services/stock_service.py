"""Reserva e devolução de estoque.

Reserva acontece ao criar o pedido; devolução só quando a cobrança não pode mais ser paga
(recusada, cancelada ou vencida e cancelada no provedor). Sempre em ordem de id de produto,
para duas compras simultâneas nunca travarem uma à outra (deadlock).
"""
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict
from app.models.cart import Cart
from app.models.order import Order
from app.repositories.product_repository import ProductRepository


def reserve(db: Session, lines: list[dict]) -> None:
    products = ProductRepository(db)
    for line in sorted(lines, key=lambda x: x["product_id"]):
        if line["unit_price_cents"] <= 0:
            raise Conflict("Produto sem preço disponível.")
        if not products.reserve(line["product_id"], line["quantity"]):
            raise Conflict(f"Estoque insuficiente para {line['name']}.")


def release(db: Session, order: Order, cart: Cart) -> None:
    """Devolve o estoque do pedido uma única vez e libera a sacola."""
    if not order.stock_released:
        products = ProductRepository(db)
        for line in sorted(order.items, key=lambda x: x["product_id"]):
            products.release(line["product_id"], line["quantity"])
        order.stock_released = True
    if cart.active_order_id == order.id:
        cart.active_order_id = None
        cart.version += 1
