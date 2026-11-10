from alembic import context
from app.core.config import get_settings
from app.core.db_engine import build_engine
from app.core.database import Base
import app.models.all  # noqa: F401  (registra todas as tabelas)


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
        settings = get_settings()
        engine = build_engine(settings.DATABASE_URL_UNPOOLED or settings.DATABASE_URL)
        with engine.connect() as connection:
            migrate(connection)
        engine.dispose()
