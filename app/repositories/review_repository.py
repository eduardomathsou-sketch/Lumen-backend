"""Acesso a dados das avaliações."""
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.review import Review
from app.models.user import User
from app.utils.pagination import Page


class ReviewRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_for_user(self, product_id: int, user_id: int) -> Review | None:
        return self.db.scalar(select(Review).where(Review.product_id == product_id, Review.user_id == user_id))

    def list_for_product(self, product_id: int, page: Page) -> list[tuple[Review, str | None]]:
        rows = self.db.execute(select(Review, User.full_name).join(User, User.id == Review.user_id)
                               .where(Review.product_id == product_id)
                               .order_by(Review.created_at.desc(), Review.id.desc())
                               .offset(page.skip).limit(page.limit))
        return [(review, name) for review, name in rows]

    def summaries(self, product_ids) -> dict[int, tuple[float, int]]:
        """Média e quantidade de avaliações de vários produtos numa consulta só."""
        ids = set(product_ids)
        if not ids:
            return {}
        rows = self.db.execute(select(Review.product_id, func.avg(Review.rating), func.count(Review.id))
                               .where(Review.product_id.in_(ids)).group_by(Review.product_id))
        return {pid: (round(float(avg), 1), count) for pid, avg, count in rows}

    def add(self, review: Review) -> Review:
        self.db.add(review)
        self.db.flush()
        return review

    def delete_for_user(self, product_id: int, user_id: int) -> None:
        self.db.execute(delete(Review).where(Review.product_id == product_id, Review.user_id == user_id))
