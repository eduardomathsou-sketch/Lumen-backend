"""Fair, bounded maintenance across serverless invocations."""
from alembic import op
import sqlalchemy as sa

revision = "0003_maintenance"
down_revision = "0002_accounts"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    if "maintenance_checked_at" not in {c["name"] for c in sa.inspect(connection).get_columns("orders")}:
        op.add_column("orders", sa.Column("maintenance_checked_at", sa.DateTime(timezone=True), nullable=True))
    if "ix_orders_maintenance_checked_at" not in {i["name"] for i in sa.inspect(connection).get_indexes("orders")}:
        op.create_index("ix_orders_maintenance_checked_at", "orders", ["maintenance_checked_at"])


def downgrade():
    raise RuntimeError("Downgrade destrutivo desabilitado; restaure um backup se necessário.")
