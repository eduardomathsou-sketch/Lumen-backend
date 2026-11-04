"""Importa todos os models de uma vez, para o SQLAlchemy e o Alembic conhecerem todas as tabelas."""
from app.models import (  # noqa: F401
    account, address, cart, category, coupon, order, payment, product, product_variant, review, shipping, user,
)
