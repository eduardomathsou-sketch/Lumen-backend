"""Preço do produto em centavos inteiros (substitui a coluna Float `price`)."""
from alembic import op
import sqlalchemy as sa

revision = '0006_price_cents'
down_revision = '0005_shipping_quotes'
branch_labels = None
depends_on = None


def upgrade():
    columns = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('products')}
    if 'price_cents' not in columns:
        op.add_column('products', sa.Column('price_cents', sa.Integer, nullable=False, server_default='0'))
    if 'price' in columns:
        # ROUND evita que 39.9 vire 3989 por causa da representação binária do float.
        op.execute(sa.text('UPDATE products SET price_cents = CAST(ROUND(price * 100) AS INTEGER)'))
        # batch_alter_table recria a tabela no SQLite, que não sabe apagar coluna sozinho.
        with op.batch_alter_table('products') as batch:
            batch.drop_column('price')


def downgrade():
    raise RuntimeError('Downgrade destrutivo desabilitado; restaure um backup se necessário.')
