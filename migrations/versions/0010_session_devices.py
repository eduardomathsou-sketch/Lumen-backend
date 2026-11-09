"""Aparelhos conectados: apelido público, datas e rótulo do aparelho em cada sessão."""
import secrets

from alembic import op
import sqlalchemy as sa

revision = '0010_session_devices'
down_revision = '0009_privacy_emails_returns'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c['name'] for c in inspector.get_columns('account_sessions')}
    for column in (sa.Column('public_id', sa.String(24), nullable=True),
                   sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
                   sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
                   sa.Column('device', sa.String(60), nullable=True)):
        if column.name not in existing:
            op.add_column('account_sessions', column)
    # Sessões já abertas ganham um apelido para aparecer na lista (as datas ficam vazias).
    rows = bind.execute(sa.text("SELECT token_hash FROM account_sessions WHERE public_id IS NULL")).fetchall()
    for (token_hash,) in rows:
        bind.execute(sa.text("UPDATE account_sessions SET public_id = :p WHERE token_hash = :t"),
                     {"p": secrets.token_urlsafe(12), "t": token_hash})
    if 'ix_account_sessions_public_id' not in {i['name'] for i in inspector.get_indexes('account_sessions')}:
        op.create_index('ix_account_sessions_public_id', 'account_sessions', ['public_id'], unique=True)


def downgrade():
    raise RuntimeError('Downgrade destrutivo desabilitado; restaure um backup se necessário.')
