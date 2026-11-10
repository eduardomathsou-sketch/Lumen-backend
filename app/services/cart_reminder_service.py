"""Lembrete de sacola, do jeito de uma maison: um só, discreto e sem desconto.

Regras (skills de carrinho abandonado + marca de luxo + LGPD):
- só contas que aceitaram comunicações (consentimento) e com link de descadastro;
- um lembrete por mudança na sacola, CART_REMINDER_HOURS depois da última mudança;
- nada de cupom: desconto para recuperar carrinho ensina a cliente a esperar desconto;
- quem já comprou não recebe (a sacola é esvaziada quando o pagamento é confirmado);
- sacolas paradas há mais de 7 dias não recebem nada.
"""
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.account import AccountCart
from app.models.cart import Cart
from app.models.payment import utc_now
from app.models.user import User
from app.services import cart_service, notification_service, privacy_service

MAX_AGE = timedelta(days=7)


def queue_reminders(db: Session, limit: int = 20) -> int:
    hours = get_settings().CART_REMINDER_HOURS
    if not hours:
        return 0
    now = utc_now()
    rows = db.execute(
        select(Cart, User)
        .join(AccountCart, AccountCart.cart_id == Cart.id)
        .join(User, User.id == AccountCart.user_id)
        .where(User.marketing_opt_in.is_(True), User.is_active.is_(True), User.deleted_at.is_(None),
               Cart.active_order_id.is_(None),
               Cart.updated_at <= now - timedelta(hours=hours), Cart.updated_at >= now - MAX_AGE,
               or_(Cart.reminded_at.is_(None), Cart.reminded_at < Cart.updated_at))
        .order_by(Cart.updated_at).limit(limit)
    ).all()
    queued = 0
    for cart, user in rows:
        cart.reminded_at = now  # marca mesmo sacola vazia, para não ser analisada de novo
        items = [item for item in cart_service.cart_read(db, cart)["items"] if item["available"]] if cart.items else []
        if not items:
            continue
        ctx = notification_service.base_context(name=user.full_name, items=items)
        if notification_service.queue(db, "cart_reminder", user.email, ctx, user_id=user.id, marketing=True,
                                      dedupe_key=f"cart_reminder:{cart.id}:{cart.version}",
                                      unsubscribe_url=privacy_service.unsubscribe_link(db, user)):
            queued += 1
    db.commit()
    return queued
