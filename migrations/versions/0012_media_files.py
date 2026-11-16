"""Fotos de produto enviadas pela administração (guardadas no banco)."""
from alembic import op
import sqlalchemy as sa

revision = '0012_media_files'
down_revision = '0011_storefront_badges'
branch_labels = None
depends_on = None


def upgrade():
    if 'media_files' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        'media_files',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('content_type', sa.String(32), nullable=False),
        sa.Column('width', sa.Integer(), nullable=False),
        sa.Column('height', sa.Integer(), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('data', sa.LargeBinary(), nullable=False),
        sa.Column('uploaded_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table('media_files')
