"""Perfil (nome e telefone), endereços salvos e variações de produto (tamanho/cor)."""
from alembic import op
import sqlalchemy as sa

revision = '0007_profile_addresses_variants'
down_revision = '0006_price_cents'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    user_columns = {c['name'] for c in inspector.get_columns('users')}
    if 'full_name' not in user_columns:
        op.add_column('users', sa.Column('full_name', sa.String(120), nullable=True))
    if 'phone' not in user_columns:
        op.add_column('users', sa.Column('phone', sa.String(20), nullable=True))
    if not inspector.has_table('addresses'):
        op.create_table('addresses',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
            sa.Column('label', sa.String(40), nullable=False),
            sa.Column('recipient', sa.String(120), nullable=False),
            sa.Column('postal_code', sa.String(8), nullable=False),
            sa.Column('street', sa.String(150), nullable=False),
            sa.Column('number', sa.String(20), nullable=False),
            sa.Column('complement', sa.String(100), nullable=False),
            sa.Column('district', sa.String(100), nullable=False),
            sa.Column('city', sa.String(100), nullable=False),
            sa.Column('state', sa.String(2), nullable=False),
            sa.Column('is_default', sa.Boolean, nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
        op.create_index('ix_addresses_user_id', 'addresses', ['user_id'])
    if not inspector.has_table('product_variants'):
        op.create_table('product_variants',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('product_id', sa.Integer, sa.ForeignKey('products.id'), nullable=False),
            sa.Column('size', sa.String(20), nullable=False),
            sa.Column('color', sa.String(40), nullable=False),
            sa.Column('stock', sa.Integer, nullable=False),
            sa.Column('is_active', sa.Boolean, nullable=False),
            sa.Column('version', sa.Integer, nullable=False, server_default='0'),
            sa.UniqueConstraint('product_id', 'size', 'color', name='uq_variant_product_size_color'))
        op.create_index('ix_product_variants_product_id', 'product_variants', ['product_id'])


def downgrade():
    raise RuntimeError('Downgrade destrutivo desabilitado; restaure um backup se necessário.')
