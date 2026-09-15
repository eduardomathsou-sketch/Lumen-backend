"""Account sessions, cart ownership and favorites; preserves existing checkout data."""
from alembic import op
import sqlalchemy as sa

revision = "0002_accounts"
down_revision = "0001_checkout"
branch_labels = None
depends_on = None


def upgrade():
    m = sa.MetaData()
    for name in ("users", "carts", "products"):
        sa.Table(name, m, autoload_with=op.get_bind())
    sa.Table("account_sessions", m,
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    sa.Table("account_carts", m,
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("cart_id", sa.Integer, sa.ForeignKey("carts.id"), nullable=False, unique=True))
    sa.Table("favorites", m,
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id"), primary_key=True))
    sa.Table("auth_attempts", m, sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("count", sa.Integer, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False))
    m.create_all(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError("Downgrade destrutivo desabilitado; restaure um backup se necessário.")
