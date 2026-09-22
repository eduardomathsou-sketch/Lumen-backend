"""Shared PostgreSQL/Neon connection policy for the API and Alembic."""
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool


def database_url(value: str):
    url = make_url(value)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    if url.get_backend_name() == "postgresql" and (url.host or "").endswith(".neon.tech"):
        if url.query.get("sslmode") not in {None, "require", "verify-ca", "verify-full"}:
            raise ValueError("A conexão Neon deve usar TLS (sslmode=require ou verify-full).")
        if "sslmode" not in url.query:
            url = url.update_query_dict({"sslmode": "require"})
    return url


def build_engine(value: str):
    url = database_url(value)
    if url.get_backend_name() == "sqlite":
        return create_engine(url, connect_args={"check_same_thread": False})
    # Neon already pools connections; do not retain per-instance idle connections
    # across serverless freezes. Disable prepared statements for transaction pooling.
    return create_engine(url, poolclass=NullPool, connect_args={
        "connect_timeout": 10, "prepare_threshold": None,
    })
