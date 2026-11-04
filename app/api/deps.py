"""Dependências compartilhadas pelas rotas (injeção de dependência do FastAPI)."""
from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Abre uma sessão do banco por requisição e fecha no final (sem commit = rollback)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def client_ip(request: Request) -> str:
    """IP da cliente para o limite de tentativas.

    Atrás de um proxy confiável (Vercel), o IP da conexão é o do proxy; por isso lemos o
    cabeçalho configurado em CLIENT_IP_HEADER, que o próprio proxy preenche. Sem proxy
    configurado, nunca confiamos em cabeçalhos enviados pela cliente.
    """
    header = get_settings().CLIENT_IP_HEADER
    if header:
        value = request.headers.get(header, "")
        # x-forwarded-for pode trazer uma lista; o primeiro é a origem segundo o proxy.
        first = value.split(",")[0].strip()
        if first:
            return first[:64]
    return request.client.host if request.client else "unknown"
