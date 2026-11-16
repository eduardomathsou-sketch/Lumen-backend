"""Acesso a dados de sacolas e do vínculo sacola ↔ conta."""
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.account import AccountCart
from app.models.cart import Cart


class CartRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, cart_id: int) -> Cart | None:
        return self.db.get(Cart, cart_id)

    def get_by_token_hash(self, token_hash: str) -> Cart | None:
        return self.db.scalar(select(Cart).where(Cart.token_hash == token_hash))

    def add(self, cart: Cart) -> Cart:
        self.db.add(cart)
        self.db.flush()
        return cart

    def lock(self, cart: Cart) -> None:
        """UPDATE carts SET version = version: trava a linha (PostgreSQL) ou o banco (SQLite)."""
        self.db.execute(update(Cart).where(Cart.id == cart.id).values(version=Cart.version))
        self.db.refresh(cart)

    def link_for_user(self, user_id: int) -> AccountCart | None:
        return self.db.get(AccountCart, user_id)

    def is_linked(self, cart_id: int) -> bool:
        return self.db.scalar(select(AccountCart).where(AccountCart.cart_id == cart_id)) is not None

    def link(self, user_id: int, cart_id: int) -> None:
        self.db.add(AccountCart(user_id=user_id, cart_id=cart_id))
