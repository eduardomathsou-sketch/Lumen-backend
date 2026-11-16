"""Consultas e exclusões dos direitos da titular (LGPD): exportar e excluir a conta."""
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.account import AccountSession, Favorite, PasswordReset
from app.models.address import Address
from app.models.notification import Notification
from app.models.product import Product
from app.models.review import Review
from app.models.user import User


class PrivacyRepository:
    def __init__(self, db: Session):
        self.db = db

    def favorites(self, user_id: int) -> list[tuple[int, str]]:
        return list(self.db.execute(select(Product.id, Product.name).join(Favorite, Favorite.product_id == Product.id)
                                    .where(Favorite.user_id == user_id).order_by(Product.id)).all())

    def reviews(self, user_id: int) -> list[Review]:
        return list(self.db.scalars(select(Review).where(Review.user_id == user_id).order_by(Review.created_at)))

    def notifications(self, user_id: int, emails: set[str]) -> list[Notification]:
        """E-mails da conta e os dos pedidos dela (que vão para o e-mail informado no checkout)."""
        return list(self.db.scalars(select(Notification).where(
            (Notification.user_id == user_id) | (Notification.recipient.in_(emails))).order_by(Notification.created_at)))

    def by_unsubscribe_hash(self, token_hash: str) -> User | None:
        return self.db.scalar(select(User).where(User.unsubscribe_token_hash == token_hash))

    def erase_personal_data(self, user_id: int) -> None:
        """Apaga o que só existe por causa da conta. Pedidos ficam (obrigação legal)."""
        for model in (AccountSession, PasswordReset, Address, Favorite, Review):
            self.db.execute(delete(model).where(model.user_id == user_id))
        # E-mails ainda na fila para a conta não devem mais sair.
        self.db.execute(delete(Notification).where(Notification.user_id == user_id,
                                                   Notification.status == "pending"))
