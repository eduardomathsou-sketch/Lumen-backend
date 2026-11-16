"""Regras de avaliação: só quem comprou e recebeu o produto pode avaliar (uma vez, editável)."""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, Forbidden, NotFound
from app.models.review import Review
from app.models.user import User
from app.repositories.cart_repository import CartRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.review_repository import ReviewRepository
from app.schemas.review import ReviewWrite
from app.utils.pagination import Page


def author_name(full_name: str | None) -> str:
    # Mostra só o primeiro nome: nada de e-mail ou sobrenome em público.
    return full_name.split()[0] if full_name and full_name.strip() else "Cliente Lumen"


def review_read(review: Review, full_name: str | None) -> dict:
    return {"id": review.id, "rating": review.rating, "comment": review.comment,
            "author": author_name(full_name), "created_at": review.created_at}


def received(db: Session, user: User, product_id: int) -> bool:
    link = CartRepository(db).link_for_user(user.id)
    if link is None:
        return False
    return any(item["product_id"] == product_id
               for order in OrderRepository(db).delivered_for_cart(link.cart_id) for item in order.items)


def _active_product(db: Session, product_id: int) -> None:
    if ProductRepository(db).get_active(product_id) is None:
        raise NotFound("Produto não encontrado.")


def list_reviews(db: Session, product_id: int, page: Page) -> dict:
    _active_product(db, product_id)
    reviews = ReviewRepository(db)
    average, count = reviews.summaries([product_id]).get(product_id, (None, 0))
    return {"average": average, "count": count,
            "items": [review_read(r, name) for r, name in reviews.list_for_product(product_id, page)]}


def save_review(db: Session, user: User, product_id: int, body: ReviewWrite) -> dict:
    _active_product(db, product_id)
    if not received(db, user, product_id):
        raise Forbidden("Você poderá avaliar depois de receber este produto.")
    reviews = ReviewRepository(db)
    review = reviews.get_for_user(product_id, user.id)
    try:
        if review is None:
            review = reviews.add(Review(product_id=product_id, user_id=user.id, **body.model_dump()))
        else:
            review.rating, review.comment = body.rating, body.comment
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("Sua avaliação acabou de ser salva em outro aparelho. Atualize a página.") from exc
    db.refresh(review)
    return review_read(review, user.full_name)


def delete_review(db: Session, user: User, product_id: int) -> None:
    ReviewRepository(db).delete_for_user(product_id, user.id)
    db.commit()
