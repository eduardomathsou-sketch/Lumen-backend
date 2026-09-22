"""Explicit admin accounts, catalog photos and optimistic stock edits."""
from alembic import op
import sqlalchemy as sa

revision = "0004_admin_catalog"
down_revision = "0003_maintenance"
branch_labels = None
depends_on = None


def upgrade():
    # Also adopts local databases initialized with create_all.
    columns = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('users')}
    if 'is_admin' not in columns:
        op.add_column('users', sa.Column('is_admin', sa.Boolean, nullable=False, server_default=sa.false()))
    columns = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('products')}
    if 'image_url' not in columns:
        op.add_column('products', sa.Column('image_url', sa.String(2048), nullable=True))
    if 'version' not in columns:
        op.add_column('products', sa.Column('version', sa.Integer, nullable=False, server_default='0'))


def downgrade():
    raise RuntimeError('Downgrade destrutivo desabilitado; restaure um backup se necessário.')
