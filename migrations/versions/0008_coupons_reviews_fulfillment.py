"""Cupons, avaliações e status de entrega dos pedidos."""
from alembic import op
import sqlalchemy as sa

revision = '0008_coupons_reviews_fulfillment'
down_revision = '0007_profile_addresses_variants'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('coupons'):
        op.create_table('coupons',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('code', sa.String(30), nullable=False),
            sa.Column('kind', sa.String(10), nullable=False),
            sa.Column('value', sa.Integer, nullable=False),
            sa.Column('min_subtotal_cents', sa.Integer, nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('max_uses', sa.Integer, nullable=True),
            sa.Column('used_count', sa.Integer, nullable=False),
            sa.Column('is_active', sa.Boolean, nullable=False),
            sa.Column('version', sa.Integer, nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
        op.create_index('ix_coupons_code', 'coupons', ['code'], unique=True)
    if not inspector.has_table('reviews'):
        op.create_table('reviews',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('product_id', sa.Integer, sa.ForeignKey('products.id'), nullable=False),
            sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
            sa.Column('rating', sa.Integer, nullable=False),
            sa.Column('comment', sa.String(1000), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint('product_id', 'user_id', name='uq_review_product_user'))
        op.create_index('ix_reviews_product_id', 'reviews', ['product_id'])
        op.create_index('ix_reviews_user_id', 'reviews', ['user_id'])
    columns = {c['name'] for c in inspector.get_columns('orders')}
    for column in [sa.Column('discount_cents', sa.Integer, nullable=False, server_default='0'),
                   sa.Column('coupon_code', sa.String(30), nullable=True),
                   sa.Column('fulfillment_status', sa.String(20), nullable=True),
                   sa.Column('tracking_code', sa.String(40), nullable=True),
                   sa.Column('shipped_at', sa.DateTime(timezone=True), nullable=True),
                   sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True)]:
        if column.name not in columns:
            op.add_column('orders', column)
    if 'ix_orders_fulfillment_status' not in {i['name'] for i in inspector.get_indexes('orders')}:
        op.create_index('ix_orders_fulfillment_status', 'orders', ['fulfillment_status'])
    # Pedidos já pagos passam a aparecer como "em preparação" para a loja.
    op.execute(sa.text("UPDATE orders SET fulfillment_status = 'preparing' "
                       "WHERE status = 'paid' AND fulfillment_status IS NULL"))


def downgrade():
    raise RuntimeError('Downgrade destrutivo desabilitado; restaure um backup se necessário.')
