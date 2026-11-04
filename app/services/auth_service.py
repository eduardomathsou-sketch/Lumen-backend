"""Regras de conta: cadastro, login, sessões revogáveis e limite de tentativas."""
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, Unauthorized, TooManyRequests
from app.core.security import digest, hash_password, new_token, verify_password
from app.models.account import AccountSession
from app.models.cart import Cart
from app.models.payment import as_utc, utc_now
from app.models.user import User
from app.repositories.cart_repository import CartRepository
from app.repositories.user_repository import AttemptRepository, SessionRepository, UserRepository

SESSION_DAYS = 7
ATTEMPT_WINDOW = timedelta(minutes=15)

__all__ = ["digest", "user_read", "get_session", "throttle", "authenticate", "logout"]


def user_read(user: User) -> dict:
    return {"id": user.id, "email": user.email, "is_admin": user.is_admin,
            "full_name": user.full_name, "phone": user.phone}


def bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise Unauthorized("Entre na sua conta para continuar.")
    return authorization[7:]


def get_session(db: Session, authorization: str | None) -> tuple[AccountSession, User]:
    session = SessionRepository(db).get(digest(bearer_token(authorization)))
    if not session or as_utc(session.expires_at) <= utc_now():
        raise Unauthorized("Sua sessão expirou. Entre novamente.")
    user = UserRepository(db).get(session.user_id)
    if not user or not user.is_active:
        raise Unauthorized("Sessão indisponível. Entre novamente.")
    return session, user


def throttle(db: Session, identity: str, limit: int) -> None:
    """Contador no banco, compartilhado entre processos; conta também os acertos."""
    row = AttemptRepository(db).get_locked(digest(identity))
    if as_utc(row.started_at) < utc_now() - ATTEMPT_WINDOW:
        row.count = 0
        row.started_at = utc_now()
    if row.count >= limit:
        db.commit()
        raise TooManyRequests("Muitas tentativas. Aguarde 15 minutos e tente novamente.", headers={"Retry-After": "900"})
    row.count += 1
    db.commit()


def open_session(db: Session, user: User) -> str:
    token = new_token(48)
    SessionRepository(db).add(AccountSession(token_hash=digest(token), user_id=user.id,
                                             expires_at=utc_now() + timedelta(days=SESSION_DAYS)))
    return token


def authenticate(db: Session, body, cart_token: str | None, *, register: bool = False) -> dict:
    users, carts = UserRepository(db), CartRepository(db)
    user = users.get_by_email(body.email)
    if register:
        password_hash = hash_password(body.password)
        if user:
            raise Conflict("Não foi possível cadastrar. Confira os dados ou entre na sua conta.")
        try:
            user = users.add(User(email=body.email, hashed_password=password_hash))
        except IntegrityError as exc:
            db.rollback()
            raise Conflict("Não foi possível cadastrar. Confira os dados ou entre na sua conta.") from exc
    else:
        # Hash de custo igual para e-mail inexistente: a demora não revela quem tem conta.
        if user:
            valid = verify_password(body.password, user.hashed_password)
        else:
            hash_password(body.password)
            valid = False
        if not user or not valid or not user.is_active:
            raise Unauthorized("E-mail ou senha incorretos.")
    users.lock(user.id)
    if carts.link_for_user(user.id) is None:
        # Primeiro acesso: a sacola de visitante (e seus pedidos) passa a ser da conta.
        cart = carts.get_by_token_hash(digest(cart_token or ""))
        if cart:
            carts.lock(cart)
            if carts.is_linked(cart.id):
                cart = None
        if cart is None:
            cart = carts.add(Cart(token_hash=digest(new_token(32)), items=[]))
        carts.link(user.id, cart.id)
    token = open_session(db, user)
    db.commit()
    return {"access_token": token, "token_type": "bearer", "user": user_read(user)}


def logout(db: Session, session: AccountSession) -> None:
    SessionRepository(db).delete(session)
    db.commit()
