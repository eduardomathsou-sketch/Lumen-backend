"""Vitrine: selo do produto e preço "de" (promoção real)."""
from alembic import op
import sqlalchemy as sa

revision = '0011_storefront_badges'
down_revision = '0010_session_devices'
branch_labels = None
depends_on = None


def upgrade():
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('products')}
    if 'compare_at_cents' not in existing:
        op.add_column('products', sa.Column('compare_at_cents', sa.Integer(), nullable=True))
    if 'badge' not in existing:
        op.add_column('products', sa.Column('badge', sa.String(24), nullable=True))


def downgrade():
    op.drop_column('products', 'badge')
    op.drop_column('products', 'compare_at_cents')
