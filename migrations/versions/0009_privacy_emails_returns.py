"""LGPD (consentimentos e exclusão), e-mails transacionais, nova senha, devoluções e índices."""
from alembic import op
import sqlalchemy as sa

revision = '0009_privacy_emails_returns'
down_revision = '0008_coupons_reviews_fulfillment'
branch_labels = None
depends_on = None


def _add_columns(inspector, table, columns):
    existing = {c['name'] for c in inspector.get_columns(table)}
    for column in columns:
        if column.name not in existing:
            op.add_column(table, column)


def _index(inspector, name, table, columns, unique=False):
    if name not in {i['name'] for i in inspector.get_indexes(table)}:
        op.create_index(name, table, columns, unique=unique)


def upgrade():
    inspector = sa.inspect(op.get_bind())
    _add_columns(inspector, 'users', [
        sa.Column('terms_version', sa.String(20), nullable=True),
        sa.Column('terms_accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('marketing_opt_in', sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column('marketing_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('unsubscribe_token_hash', sa.String(64), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    ])
    _index(inspector, 'ix_users_unsubscribe_token_hash', 'users', ['unsubscribe_token_hash'], unique=True)

    _add_columns(inspector, 'carts', [
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reminded_at', sa.DateTime(timezone=True), nullable=True),
    ])
    op.execute(sa.text("UPDATE carts SET updated_at = created_at WHERE updated_at IS NULL"))
    _index(inspector, 'ix_carts_updated_at', 'carts', ['updated_at'])

    _add_columns(inspector, 'products', [
        sa.Column('composition', sa.String(200), nullable=True),
        sa.Column('care', sa.String(300), nullable=True),
    ])
    # Índices medidos pelas consultas reais: vitrine por categoria e listas por data.
    _index(inspector, 'ix_products_category_id', 'products', ['category_id'])
    _index(inspector, 'ix_orders_created_at', 'orders', ['created_at'])

    if not inspector.has_table('password_resets'):
        op.create_table('password_resets',
            sa.Column('token_hash', sa.String(64), primary_key=True),
            sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('used_at', sa.DateTime(timezone=True), nullable=True))
        op.create_index('ix_password_resets_user_id', 'password_resets', ['user_id'])
        op.create_index('ix_password_resets_expires_at', 'password_resets', ['expires_at'])

    if not inspector.has_table('notifications'):
        op.create_table('notifications',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('kind', sa.String(30), nullable=False),
            sa.Column('recipient', sa.String(255), nullable=False),
            sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=True),
            sa.Column('dedupe_key', sa.String(120), nullable=True),
            sa.Column('subject', sa.String(200), nullable=False),
            sa.Column('body_text', sa.Text, nullable=True),
            sa.Column('body_html', sa.Text, nullable=True),
            sa.Column('headers', sa.String(500), nullable=True),
            sa.Column('status', sa.String(10), nullable=False),
            sa.Column('attempts', sa.Integer, nullable=False),
            sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('last_error', sa.String(200), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True))
        op.create_index('ix_notifications_kind', 'notifications', ['kind'])
        op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
        op.create_index('ix_notifications_dedupe_key', 'notifications', ['dedupe_key'], unique=True)
        op.create_index('ix_notifications_status', 'notifications', ['status'])
        op.create_index('ix_notifications_next_attempt_at', 'notifications', ['next_attempt_at'])
        op.create_index('ix_notifications_created_at', 'notifications', ['created_at'])

    if not inspector.has_table('return_requests'):
        op.create_table('return_requests',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('order_id', sa.String(36), sa.ForeignKey('orders.id'), nullable=False),
            sa.Column('reason', sa.String(20), nullable=False),
            sa.Column('details', sa.String(500), nullable=False),
            sa.Column('status', sa.String(20), nullable=False),
            sa.Column('admin_note', sa.String(300), nullable=True),
            sa.Column('restocked', sa.Boolean, nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('refunded_at', sa.DateTime(timezone=True), nullable=True))
        op.create_index('ix_return_requests_order_id', 'return_requests', ['order_id'], unique=True)
        op.create_index('ix_return_requests_status', 'return_requests', ['status'])


def downgrade():
    raise RuntimeError('Downgrade destrutivo desabilitado; restaure um backup se necessário.')
