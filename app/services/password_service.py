"""Esqueci minha senha: token de uso único, 30 minutos, guardado só como hash.

1. A cliente informa o e-mail. A resposta é sempre a mesma, com ou sem conta.
2. Se a conta existe, geramos um token aleatório (32 bytes), guardamos o SHA-256 e enviamos
   o link por e-mail em segundo plano. O link nunca é gravado no banco nem no log.
3. Na confirmação: token válido, não usado e no prazo -> nova senha, todas as sessões
   encerradas e aviso de "senha alterada" por e-mail.
"""
from datetime import timedelta

from fastapi import BackgroundTasks
from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.core.audit import pseudonym, security_event, warning
from app.core.config import get_settings
from app.core.exceptions import Unprocessable
from app.core.security import digest, hash_password, new_token
from app.models.account import PasswordReset
from app.models.payment import utc_now
from app.repositories.user_repository import SessionRepository, UserRepository
from app.schemas.auth import PasswordResetConfirm
from app.services import notification_service

RESET_MINUTES = 30
INVALID = "Este link de nova senha é inválido ou expirou. Peça um novo."


def reset_url(token: str) -> str | None:
    template = get_settings().PASSWORD_RESET_URL.strip()
    if not template:
        return None
    return template.replace("{token}", token) if "{token}" in template else f"{template}?token={token}"


def request_reset(db: Session, email: str, background: BackgroundTasks) -> None:
    user = UserRepository(db).get_by_email(email)
    if user is None or not user.is_active or user.deleted_at is not None:
        # Gasta o mesmo tipo de trabalho (gerar token + hash) para não criar diferença de tempo.
        digest(new_token(32))
        security_event("password.reset_requested", who=pseudonym(email), account=False)
        return
    # Um pedido novo invalida os anteriores ainda não usados.
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None)))
    token = new_token(32)
    db.add(PasswordReset(token_hash=digest(token), user_id=user.id,
                         expires_at=utc_now() + timedelta(minutes=RESET_MINUTES)))
    db.commit()
    security_event("password.reset_requested", user=user.id, account=True)
    ctx = notification_service.base_context(name=user.full_name, token=token, url=reset_url(token))
    background.add_task(notification_service.send_direct, "password_reset", user.email, ctx)


def confirm_reset(db: Session, body: PasswordResetConfirm) -> None:
    token_hash = digest(body.token)
    now = utc_now()
    # Testa e marca como usado numa instrução só: dois cliques no mesmo link não trocam a senha duas vezes.
    claimed = db.execute(update(PasswordReset).where(
        PasswordReset.token_hash == token_hash, PasswordReset.used_at.is_(None), PasswordReset.expires_at > now,
    ).values(used_at=now)).rowcount
    reset = db.get(PasswordReset, token_hash) if claimed else None
    if reset is None:
        db.rollback()
        warning("password.reset_invalid")
        raise Unprocessable(INVALID)
    users = UserRepository(db)
    users.lock(reset.user_id)
    user = users.get(reset.user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        db.rollback()
        raise Unprocessable(INVALID)
    user.hashed_password = hash_password(body.new_password)
    # Quem tinha a senha antiga (ou um aparelho perdido) perde o acesso na hora.
    SessionRepository(db).delete_all_for_user(user.id)
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id,
                                           PasswordReset.token_hash != reset.token_hash))
    notification_service.queue(db, "password_changed", user.email,
                               notification_service.base_context(name=user.full_name), user_id=user.id)
    db.commit()
    security_event("password.reset_completed", user=user.id)


def delete_expired(db: Session, now) -> int:
    return db.execute(delete(PasswordReset).where(PasswordReset.expires_at < now - timedelta(days=1))).rowcount
