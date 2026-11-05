from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.payment import utc_now


class Notification(Base):
    """Fila de e-mails (padrão outbox).

    O e-mail é gravado na mesma transação que muda o pedido; a rotina de manutenção envia
    depois, com novas tentativas se o provedor falhar. Assim um pagamento confirmado nunca
    fica sem e-mail por causa de uma queda momentânea do SMTP, e um erro no e-mail nunca
    desfaz o pagamento. Depois de enviado, o corpo é apagado: só fica o registro.
    """
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    recipient: Mapped[str] = mapped_column(String(255))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    # Impede o mesmo aviso duas vezes (ex.: dois webhooks confirmando o mesmo pagamento).
    dedupe_key: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    subject: Mapped[str] = mapped_column(String(200))
    body_text: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    headers: Mapped[str | None] = mapped_column(String(500))
    # pending -> sent | failed (após 5 tentativas) | direct (enviado na hora, sem guardar corpo)
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    last_error: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
