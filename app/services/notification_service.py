"""Fila de e-mails: grava junto com a mudança de negócio e envia na rotina de manutenção."""
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import pseudonym, warning
from app.core.config import get_settings
from app.models.notification import Notification
from app.models.order import Order
from app.models.payment import utc_now
from app.services import email_templates
from app.services.email_provider import EmailDeliveryError, OutgoingEmail, get_provider

MAX_ATTEMPTS = 5
RETENTION_DAYS = 90


def _footer(marketing: bool = False, unsubscribe_url: str | None = None) -> str:
    settings = get_settings()
    parts = []
    if marketing:
        parts.append("Você recebe este lembrete porque aceitou comunicações da Lumen.")
        parts.append(f"Para não receber mais: {unsubscribe_url}" if unsubscribe_url
                     else "Para não receber mais, desative em Minha conta › Privacidade.")
    else:
        parts.append("Mensagem automática sobre a sua conta ou o seu pedido.")
    if settings.contact_email:
        parts.append(f"Atendimento: {settings.contact_email}")
    return " ".join(parts)


def base_context(**ctx) -> dict:
    return {"store": get_settings().STORE_NAME, **ctx}


def order_context(order: Order) -> dict:
    return base_context(
        order_id=order.id, name=(order.address or {}).get("recipient"), items=order.items,
        discount_cents=order.discount_cents, coupon_code=order.coupon_code,
        shipping_label=order.shipping_label, shipping_cents=order.shipping_cents,
        shipping_days=order.shipping_days, total_cents=order.total_cents,
        tracking_code=order.tracking_code)


def queue(db: Session, kind: str, recipient: str, ctx: dict, *, dedupe_key: str | None = None,
          user_id: int | None = None, marketing: bool = False, unsubscribe_url: str | None = None) -> Notification | None:
    """Coloca o e-mail na fila, na transação atual. Repetido (mesma dedupe_key) é ignorado."""
    if dedupe_key and db.scalar(select(Notification.id).where(Notification.dedupe_key == dedupe_key)):
        return None
    subject, text, html = email_templates.render(kind, {**ctx, "footer": _footer(marketing, unsubscribe_url)})
    headers = None
    if marketing and unsubscribe_url:
        headers = f"List-Unsubscribe: <{unsubscribe_url}>"
    item = Notification(kind=kind, recipient=recipient, user_id=user_id, dedupe_key=dedupe_key,
                        subject=subject, body_text=text, body_html=html, headers=headers,
                        status="pending", attempts=0, next_attempt_at=utc_now())
    try:
        with db.begin_nested():  # savepoint: corrida na dedupe_key não desfaz o resto da transação
            db.add(item)
            db.flush()
    except IntegrityError:
        return None
    return item


def queue_order_email(db: Session, kind: str, order: Order) -> None:
    queue(db, kind, order.payer_email, order_context(order), dedupe_key=f"{kind}:{order.id}")


def send_direct(kind: str, recipient: str, ctx: dict) -> bool:
    """Envio imediato sem gravar o corpo (link de senha nunca fica no banco). Roda em segundo plano."""
    subject, text, html = email_templates.render(kind, {**ctx, "footer": _footer()})
    try:
        get_provider().send(OutgoingEmail(to=recipient, subject=subject, text=text, html=html))
        return True
    except EmailDeliveryError as exc:
        warning("email.direct_failed", kind=kind, to=pseudonym(recipient), error=str(exc))
        return False


def _headers(item: Notification) -> dict[str, str]:
    if not item.headers:
        return {}
    name, _, value = item.headers.partition(": ")
    return {name: value}


def dispatch_pending(db: Session, limit: int = 20) -> dict:
    """Envia o que está na fila; falha agenda nova tentativa (1, 2, 4, 8 min) até 5 vezes."""
    now = utc_now()
    ids = list(db.scalars(select(Notification.id).where(Notification.status == "pending",
                                                         Notification.next_attempt_at <= now)
                          .order_by(Notification.next_attempt_at).limit(limit)))
    sent = failed = 0
    provider = get_provider()
    for notification_id in ids:
        # Reivindica a mensagem: duas execuções simultâneas nunca enviam o mesmo e-mail.
        claimed = db.execute(update(Notification).where(
            Notification.id == notification_id, Notification.status == "pending",
            Notification.next_attempt_at <= now,
        ).values(next_attempt_at=now + timedelta(minutes=10))).rowcount
        db.commit()
        if not claimed:
            continue
        item = db.get(Notification, notification_id)
        try:
            provider.send(OutgoingEmail(to=item.recipient, subject=item.subject, text=item.body_text or "",
                                        html=item.body_html, headers=_headers(item)))
        except EmailDeliveryError as exc:
            item.attempts += 1
            item.last_error = str(exc)[:200]
            if item.attempts >= MAX_ATTEMPTS:
                item.status = "failed"
                warning("email.failed", kind=item.kind, notification=item.id)
            else:
                item.next_attempt_at = utc_now() + timedelta(minutes=2 ** (item.attempts - 1))
            failed += 1
        else:
            item.attempts += 1
            item.status = "sent"
            item.sent_at = utc_now()
            item.last_error = None
            # Minimização: o conteúdo já foi entregue; guardamos só o registro do envio.
            item.body_text = item.body_html = None
            sent += 1
        db.commit()
    return {"sent": sent, "failed": failed}


def delete_old(db: Session, now) -> int:
    return db.execute(delete(Notification).where(Notification.created_at < now - timedelta(days=RETENTION_DAYS))).rowcount
