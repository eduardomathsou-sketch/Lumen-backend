from alembic import context
from sqlalchemy import create_engine, pool
from app.core.config import get_settings
from app.core.database import Base
from app.models import cart, category, order, payment, product, user  # noqa: F401


if context.is_offline_mode():
    raise RuntimeError("Esta migração inicial precisa de conexão para preservar tabelas existentes.")
else:
    def migrate(connection):
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    supplied_connection = context.config.attributes.get("connection")
    if supplied_connection is not None:
        migrate(supplied_connection)
    else:
        engine = create_engine(get_settings().DATABASE_URL, poolclass=pool.NullPool)
        with engine.connect() as connection:
            migrate(connection)
