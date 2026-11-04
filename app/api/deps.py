"""Dependências compartilhadas pelas rotas (injeção de dependência do FastAPI)."""
from collections.abc import Generator

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.exceptions import Forbidden, Unauthorized
from app.models.cart import Cart
from app.models.user import User


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


def optional_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User | None:
    from app.services.auth_service import get_session
    return get_session(db, authorization)[1] if authorization else None


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise Unauthorized("Entre na sua conta para continuar.")
    return user


def current_admin(user: User = Depends(current_user)) -> User:
    # is_admin é lido do banco a cada requisição: tirar a permissão vale na hora.
    if not user.is_admin:
        raise Forbidden("Acesso restrito à administração da loja.")
    return user


def cart_session(x_cart_token: str | None = Header(default=None), user: User | None = Depends(optional_user),
                 db: Session = Depends(get_db)) -> Cart:
    """Sacola da requisição: a da conta (Bearer) ou a de visitante (X-Cart-Token)."""
    from app.services import cart_service
    if user:
        return cart_service.account_cart(db, user)
    return cart_service.guest_cart(db, x_cart_token)
