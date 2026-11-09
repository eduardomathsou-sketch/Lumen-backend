from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.user import User  # noqa: F401
from app.models.payment import utc_now


class AccountSession(Base):
    """Sessão de login: o "código de acesso" que o app guarda.

    O app recebe um token aleatório; o banco guarda só o SHA-256 dele (token_hash). Quem lê o
    banco não consegue usar a sessão de ninguém. public_id é um apelido sem valor de acesso,
    usado para listar e encerrar aparelhos em "Minha conta".
    """
    __tablename__ = "account_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    public_id: Mapped[str | None] = mapped_column(String(24), unique=True, index=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now)
    # Rótulo curto do aparelho ("Chrome · Windows"); nunca o User-Agent inteiro nem o IP.
    device: Mapped[str | None] = mapped_column(String(60))


class AccountCart(Base):
    __tablename__ = "account_carts"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    cart_id: Mapped[int] = mapped_column(ForeignKey("carts.id"), unique=True)


class Favorite(Base):
    __tablename__ = "favorites"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)


class PasswordReset(Base):
    """Pedido de nova senha: token de uso único, válido por 30 minutos, guardado só como hash."""
    __tablename__ = "password_resets"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthAttempt(Base):
    __tablename__ = "auth_attempts"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
