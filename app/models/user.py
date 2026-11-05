from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, false
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(default=False, server_default=false(), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20))
    # Consentimentos (LGPD): qual versão dos termos foi aceita e quando; marketing é opcional
    # e começa desligado (consentimento livre, informado e revogável).
    terms_version: Mapped[str | None] = mapped_column(String(20))
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    marketing_opt_in: Mapped[bool] = mapped_column(default=False, server_default=false(), nullable=False)
    marketing_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Link de descadastro de um clique (guardado só como hash, como os outros tokens).
    unsubscribe_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    # Conta excluída a pedido da titular: dados pessoais anonimizados, pedidos mantidos pelo prazo legal.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
