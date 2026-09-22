"""Explicit, one-time copy into an empty migrated PostgreSQL database."""
import argparse
from datetime import datetime
from pathlib import Path

from sqlalchemy import MetaData, create_engine, func, select, text
from sqlalchemy.engine import URL

from app.core.config import get_settings
from app.core.database import Base
from app.core.db_engine import build_engine
from app.models import account, cart, category, order, payment, product, user  # noqa: F401
from app.models.payment import as_utc


def copy_database(source_engine, destination_engine):
    source_metadata = MetaData()
    source_metadata.reflect(source_engine)
    counts = {}
    with source_engine.connect() as source, destination_engine.begin() as destination:
        tables = Base.metadata.sorted_tables
        # Never merge into existing data; a retry cannot duplicate or overwrite orders.
        for table in tables:
            if destination.scalar(select(func.count()).select_from(table)):
                raise RuntimeError("O banco de destino já contém dados. Importação cancelada sem alterações.")
        for table in tables:
            if table.name not in source_metadata.tables:
                continue
            original = source_metadata.tables[table.name]
            allowed = set(table.columns.keys())
            count = 0
            result = source.execute(select(original)).mappings()
            for batch in result.partitions(500):
                rows = [{key: as_utc(value) if isinstance(value, datetime) else value
                         for key, value in row.items() if key in allowed} for row in batch]
                if rows:
                    destination.execute(table.insert(), rows)
                    count += len(rows)
            counts[table.name] = count
        # Explicit IDs do not advance PostgreSQL serial sequences.
        if destination.dialect.name == "postgresql":
            for table in tables:
                if "id" not in table.c or table.c.id.type.python_type is not int:
                    continue
                sequence = destination.scalar(text("SELECT pg_get_serial_sequence(:table, 'id')"), {"table": table.name})
                if sequence:
                    maximum = destination.scalar(select(func.max(table.c.id)))
                    destination.execute(text("SELECT setval(CAST(:sequence AS regclass), :value, :called)"),
                        {"sequence": sequence, "value": maximum or 1, "called": maximum is not None})
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Existing SQLite file (read only)")
    args = parser.parse_args()
    path = Path(args.source).resolve(strict=True)
    settings = get_settings()
    destination = build_engine(settings.DATABASE_URL_UNPOOLED or settings.DATABASE_URL)
    if destination.dialect.name != "postgresql":
        raise RuntimeError("Configure uma conexão PostgreSQL direta como destino.")
    # SQLite URI mode=ro prevents accidental writes to the original database.
    source = create_engine(URL.create("sqlite", database=f"file:{path.as_posix()}",
                                     query={"mode": "ro", "uri": "true"}))
    try:
        for table, count in copy_database(source, destination).items():
            print(f"{table}: {count} registros copiados")
    finally:
        source.dispose()
        destination.dispose()


if __name__ == "__main__":
    main()
