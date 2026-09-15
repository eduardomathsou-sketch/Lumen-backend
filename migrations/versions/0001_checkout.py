"""Initial frozen schema; adopts tables previously created with create_all."""
from alembic import op
import sqlalchemy as sa

revision = "0001_checkout"
down_revision = None
branch_labels = None
depends_on = None


def schema():
    m = sa.MetaData()
    C = sa.Column
    sa.Table("categories", m, C("id", sa.Integer, primary_key=True),
        C("name", sa.String(100), nullable=False, unique=True, index=True), C("description", sa.String(255)))
    sa.Table("products", m, C("id", sa.Integer, primary_key=True),
        C("name", sa.String(150), nullable=False, index=True), C("description", sa.String(500)),
        C("price", sa.Float, nullable=False), C("stock", sa.Integer, nullable=False),
        C("category_id", sa.Integer, sa.ForeignKey("categories.id")), C("is_active", sa.Boolean, nullable=False))
    sa.Table("users", m, C("id", sa.Integer, primary_key=True),
        C("email", sa.String(255), nullable=False, unique=True, index=True),
        C("hashed_password", sa.String(255), nullable=False), C("is_active", sa.Boolean, nullable=False))
    sa.Table("payments", m, C("id", sa.Integer, primary_key=True),
        C("order_reference", sa.String(100), nullable=False, index=True), C("amount", sa.Numeric(12,2), nullable=False),
        C("currency", sa.String(3), nullable=False), C("method", sa.String(20), nullable=False),
        C("status", sa.String(30), nullable=False, index=True), C("provider", sa.String(40), nullable=False),
        C("provider_charge_id", sa.String(100), nullable=False, unique=True, index=True),
        C("idempotency_key", sa.String(255), nullable=False, unique=True, index=True),
        C("request_fingerprint", sa.String(64), nullable=False), C("provider_data", sa.JSON, nullable=False),
        C("paid_at", sa.DateTime(timezone=True)), C("created_at", sa.DateTime(timezone=True), nullable=False),
        C("updated_at", sa.DateTime(timezone=True), nullable=False))
    sa.Table("payment_webhook_events", m, C("id", sa.Integer, primary_key=True),
        C("provider_event_id", sa.String(100), nullable=False, unique=True, index=True),
        C("payment_id", sa.Integer, sa.ForeignKey("payments.id"), nullable=False, index=True),
        C("event_type", sa.String(60), nullable=False), C("payload", sa.JSON, nullable=False),
        C("processed_at", sa.DateTime(timezone=True)), C("received_at", sa.DateTime(timezone=True), nullable=False))
    sa.Table("carts", m, C("id", sa.Integer, primary_key=True),
        C("token_hash", sa.String(64), nullable=False, unique=True, index=True),
        C("version", sa.Integer, nullable=False), C("items", sa.JSON, nullable=False),
        C("active_order_id", sa.String(36)), C("created_at", sa.DateTime(timezone=True), nullable=False))
    sa.Table("orders", m, C("id", sa.String(36), primary_key=True),
        C("cart_id", sa.Integer, sa.ForeignKey("carts.id"), nullable=False, index=True),
        C("checkout_key", sa.String(64), nullable=False, unique=True), C("request_hash", sa.String(64), nullable=False),
        C("items", sa.JSON, nullable=False), C("address", sa.JSON, nullable=False),
        C("payer_email", sa.String(255), nullable=False), C("payer_document", sa.String(14), nullable=False),
        C("subtotal_cents", sa.Integer, nullable=False), C("shipping_cents", sa.Integer, nullable=False),
        C("total_cents", sa.Integer, nullable=False), C("shipping_label", sa.String(100), nullable=False),
        C("shipping_days", sa.Integer, nullable=False), C("provider", sa.String(30), nullable=False),
        C("status", sa.String(30), nullable=False, index=True), C("stock_released", sa.Boolean, nullable=False),
        C("created_at", sa.DateTime(timezone=True), nullable=False), C("expires_at", sa.DateTime(timezone=True), nullable=False))
    return m


def upgrade():
    schema().create_all(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError("Downgrade destrutivo desabilitado; restaure um backup se necessário.")
