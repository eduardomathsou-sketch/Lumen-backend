"""Acesso a dados dos endereços salvos na conta."""
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.address import Address


class AddressRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_for_user(self, user_id: int) -> list[Address]:
        return list(self.db.scalars(select(Address).where(Address.user_id == user_id)
                                    .order_by(Address.is_default.desc(), Address.id)))

    def get_for_user(self, address_id: int, user_id: int) -> Address | None:
        return self.db.scalar(select(Address).where(Address.id == address_id, Address.user_id == user_id))

    def count_for_user(self, user_id: int) -> int:
        return self.db.scalar(select(func.count()).select_from(Address).where(Address.user_id == user_id))

    def clear_default(self, user_id: int) -> None:
        self.db.execute(update(Address).where(Address.user_id == user_id).values(is_default=False))

    def add(self, address: Address) -> Address:
        self.db.add(address)
        self.db.flush()
        return address

    def delete(self, address: Address) -> None:
        self.db.delete(address)
