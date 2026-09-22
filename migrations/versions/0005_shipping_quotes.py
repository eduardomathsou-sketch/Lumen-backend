"""PAC/SEDEX quote snapshots and editable package measurements."""
from alembic import op
import sqlalchemy as sa

revision = '0005_shipping_quotes'
down_revision = '0004_admin_catalog'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {c['name'] for c in inspector.get_columns('products')}
    for name, default in [('weight_grams', '500'), ('height_cm', '10'), ('width_cm', '15'), ('length_cm', '20')]:
        if name not in columns:
            op.add_column('products', sa.Column(name, sa.Integer, nullable=False, server_default=default))
    if 'shipping_details' not in {c['name'] for c in inspector.get_columns('orders')}:
        op.add_column('orders', sa.Column('shipping_details', sa.JSON, nullable=True))
    if not inspector.has_table('shipping_quotes'):
        op.create_table('shipping_quotes',
            sa.Column('id', sa.String(64), primary_key=True),
            sa.Column('cart_id', sa.Integer, sa.ForeignKey('carts.id'), nullable=False),
            sa.Column('postal_code', sa.String(8), nullable=False),
            sa.Column('fingerprint', sa.String(64), nullable=False),
            sa.Column('options', sa.JSON, nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))
        op.create_index('ix_shipping_quotes_cart_id', 'shipping_quotes', ['cart_id'])
        op.create_index('ix_shipping_quotes_expires_at', 'shipping_quotes', ['expires_at'])


def downgrade():
    raise RuntimeError('Downgrade destrutivo desabilitado; restaure um backup se necessário.')
