"""Importa todos os models de uma vez, para o SQLAlchemy e o Alembic conhecerem todas as tabelas."""
from app.models import (  # noqa: F401
    account, address, cart, category, coupon, notification, order, payment, product, product_variant,
    return_request, review, shipping, user,
)
