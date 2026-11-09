"""Regras de conta: cadastro, login, sessões revogáveis e limite de tentativas."""
from contextlib import contextmanager
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import pseudonym, security_event, warning
from app.core.config import get_settings
from app.core.exceptions import Conflict, Unauthorized, TooManyRequests
from app.core.security import digest, hash_password, new_token, verify_password
from app.models.account import AccountSession
from app.models.cart import Cart
from app.models.payment import as_utc, utc_now
from app.models.user import User
from app.repositories.cart_repository import CartRepository
from app.repositories.user_repository import AttemptRepository, SessionRepository, UserRepository

ATTEMPT_WINDOW = timedelta(minutes=15)
# Um token legítimo tem 64 caracteres; nada maior que isso chega a ser consultado no banco.
MAX_TOKEN_LENGTH = 128
# "Usado por último" é gravado no máximo a cada 10 minutos (não vira uma escrita por requisição).
TOUCH_EVERY = timedelta(minutes=10)

__all__ = ["digest", "user_read", "get_session", "throttle", "authenticate", "logout"]


def user_read(user: User) -> dict:
    from app.services.legal_service import TERMS_VERSION
    return {"id": user.id, "email": user.email, "is_admin": user.is_admin,
            "full_name": user.full_name, "phone": user.phone,
            "marketing_opt_in": user.marketing_opt_in, "terms_version": user.terms_version,
            # False quando os Termos mudaram depois do aceite: o app pede o aceite de novo.
            "terms_current": user.terms_version == TERMS_VERSION}


def bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise Unauthorized("Entre na sua conta para continuar.")
    token = authorization[7:]
    if not token or len(token) > MAX_TOKEN_LENGTH:
        raise Unauthorized("Entre na sua conta para continuar.")
    return token


def device_label(user_agent: str | None) -> str:
    """Rótulo curto do aparelho para a lista "Aparelhos conectados" (nunca o User-Agent inteiro)."""
    ua = (user_agent or "").lower()
    if "dart/" in ua or "dart:io" in ua:
        return "Aplicativo Lumen"
    browser = next((name for mark, name in (("edg/", "Edge"), ("opr/", "Opera"), ("firefox/", "Firefox"),
                                            ("chrome/", "Chrome"), ("safari/", "Safari")) if mark in ua), "")
    system = next((name for mark, name in (("android", "Android"), ("iphone", "iPhone"), ("ipad", "iPad"),
                                           ("windows", "Windows"), ("mac os", "Mac"), ("linux", "Linux"))
                   if mark in ua), "")
    return " · ".join(part for part in (browser, system) if part) or "Aparelho não identificado"


def get_session(db: Session, authorization: str | None) -> tuple[AccountSession, User]:
    sessions = SessionRepository(db)
    session = sessions.get(digest(bearer_token(authorization)))
    now = utc_now()
    if not session or as_utc(session.expires_at) <= now:
        raise Unauthorized("Sua sessão expirou. Entre novamente.")
    user = UserRepository(db).get(session.user_id)
    if not user or not user.is_active or user.deleted_at is not None:
        raise Unauthorized("Sessão indisponível. Entre novamente.")
    if session.last_used_at is None or as_utc(session.last_used_at) < now - TOUCH_EVERY:
        sessions.touch(session.token_hash, now)
        db.commit()
    return session, user


def admin_session_fresh(session: AccountSession) -> bool:
    """A sessão da administração vale poucas horas, mesmo que o prazo normal ainda não tenha vencido."""
    if session.created_at is None:
        return True  # sessão anterior a este controle: vale até o vencimento dela
    limit = timedelta(hours=get_settings().ADMIN_SESSION_HOURS)
    return as_utc(session.created_at) + limit > utc_now()


def throttle(db: Session, identity: str, limit: int) -> None:
    """Contador no banco, compartilhado entre processos; conta também os acertos."""
    row = AttemptRepository(db).get_locked(digest(identity))
    if as_utc(row.started_at) < utc_now() - ATTEMPT_WINDOW:
        row.count = 0
        row.started_at = utc_now()
    if row.count >= limit:
        db.commit()
        warning("auth.rate_limited", scope=identity.split(":", 1)[0], who=pseudonym(identity))
        raise TooManyRequests("Muitas tentativas. Aguarde 15 minutos e tente novamente.", headers={"Retry-After": "900"})
    row.count += 1
    db.commit()


def check_strikes(db: Session, identity: str, limit: int) -> None:
    """Só confere: bloqueia quem já acumulou `limit` falhas na janela. Não conta a chamada atual."""
    row = AttemptRepository(db).get_locked(digest(identity))
    blocked = row.count >= limit and as_utc(row.started_at) >= utc_now() - ATTEMPT_WINDOW
    db.commit()
    if blocked:
        warning("abuse.blocked", scope=identity.split(":", 1)[0], who=pseudonym(identity))
        raise TooManyRequests("Muitas tentativas. Aguarde 15 minutos e tente novamente.", headers={"Retry-After": "900"})


def add_strike(db: Session, identity: str) -> None:
    """Registra uma falha (ex.: código de cupom que não existe)."""
    row = AttemptRepository(db).get_locked(digest(identity))
    if as_utc(row.started_at) < utc_now() - ATTEMPT_WINDOW:
        row.count = 0
        row.started_at = utc_now()
    row.count += 1
    db.commit()


@contextmanager
def coupon_attempts(db: Session, ip: str, code: str | None):
    """Envolve qualquer cálculo que use cupom: o acerto não conta, o chute errado conta."""
    from app.services.coupon_service import UnknownCoupon
    if not code:
        yield
        return
    identity = f"coupon:{ip}"
    check_strikes(db, identity, get_settings().COUPON_ATTEMPT_LIMIT)
    try:
        yield
    except UnknownCoupon:
        db.rollback()
        add_strike(db, identity)
        raise


def open_session(db: Session, user: User, user_agent: str | None = None) -> str:
    """Cria o código de acesso: 48 bytes aleatórios para o app, só o hash para o banco."""
    settings = get_settings()
    now = utc_now()
    lifetime = (timedelta(hours=settings.ADMIN_SESSION_HOURS) if user.is_admin
                else timedelta(days=settings.SESSION_DAYS))
    token = new_token(48)
    sessions = SessionRepository(db)
    sessions.add(AccountSession(token_hash=digest(token), user_id=user.id, public_id=new_token(12),
                                expires_at=now + lifetime, created_at=now, last_used_at=now,
                                device=device_label(user_agent)))
    db.flush()
    # Sem teto, um robô com a senha criaria sessões sem parar; as mais antigas saem.
    sessions.trim(user.id, settings.MAX_SESSIONS_PER_USER)
    return token


def session_read(session: AccountSession, current: AccountSession) -> dict:
    return {"id": session.public_id, "device": session.device or "Aparelho não identificado",
            "created_at": session.created_at, "last_used_at": session.last_used_at,
            "expires_at": session.expires_at, "current": session.token_hash == current.token_hash}


def list_sessions(db: Session, user: User, current: AccountSession) -> list[dict]:
    return [session_read(s, current) for s in SessionRepository(db).list_for_user(user.id, utc_now())]


def revoke_session(db: Session, user: User, public_id: str) -> None:
    """Encerra um aparelho da própria conta (a busca já filtra pelo dono)."""
    from app.core.exceptions import NotFound
    sessions = SessionRepository(db)
    target = sessions.get_public(user.id, public_id)
    if target is None:
        raise NotFound("Aparelho não encontrado.")
    sessions.delete(target)
    db.commit()
    security_event("auth.session_revoked", user=user.id)


def logout_others(db: Session, user: User, current: AccountSession) -> None:
    SessionRepository(db).delete_all_for_user(user.id, keep_token_hash=current.token_hash)
    db.commit()
    security_event("auth.logout_others", user=user.id)


def authenticate(db: Session, body, cart_token: str | None, *, register: bool = False,
                 user_agent: str | None = None) -> dict:
    users, carts = UserRepository(db), CartRepository(db)
    user = users.get_by_email(body.email)
    if register:
        password_hash = hash_password(body.password)
        if user:
            raise Conflict("Não foi possível cadastrar. Confira os dados ou entre na sua conta.")
        from app.services.legal_service import TERMS_VERSION
        now = utc_now()
        try:
            user = users.add(User(email=body.email, hashed_password=password_hash,
                                  terms_version=TERMS_VERSION, terms_accepted_at=now,
                                  marketing_opt_in=body.marketing_opt_in,
                                  marketing_updated_at=now if body.marketing_opt_in else None))
        except IntegrityError as exc:
            db.rollback()
            raise Conflict("Não foi possível cadastrar. Confira os dados ou entre na sua conta.") from exc
        security_event("auth.register", user=user.id, marketing=body.marketing_opt_in)
    else:
        # Hash de custo igual para e-mail inexistente: a demora não revela quem tem conta.
        if user:
            valid = verify_password(body.password, user.hashed_password)
        else:
            hash_password(body.password)
            valid = False
        if not user or not valid or not user.is_active or user.deleted_at is not None:
            warning("auth.login_failed", who=pseudonym(body.email))
            raise Unauthorized("E-mail ou senha incorretos.")
        security_event("auth.login", user=user.id)
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
    token = open_session(db, user, user_agent)
    db.commit()
    return {"access_token": token, "token_type": "bearer", "user": user_read(user)}


def logout(db: Session, session: AccountSession) -> None:
    SessionRepository(db).delete(session)
    db.commit()
    security_event("auth.logout", user=session.user_id)
