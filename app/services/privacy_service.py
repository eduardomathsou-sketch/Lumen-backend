"""Direitos da titular (LGPD, art. 18) e preferências de comunicação.

- Consentimentos: marketing liga/desliga a qualquer momento; o aceite dos Termos é renovado
  quando a versão muda.
- Portabilidade/acesso: cópia completa dos dados em JSON (pede a senha de novo).
- Eliminação: apaga o que é só da conta e anonimiza o cadastro; pedidos ficam pelo prazo
  legal (art. 16, I), sem ligação com um e-mail ou nome.
- Descadastro de um clique pelo link do e-mail, sem precisar entrar na conta.
"""
from sqlalchemy.orm import Session

from app.core.audit import security_event
from app.core.config import get_settings
from app.core.exceptions import Conflict, Unauthorized
from app.core.security import digest, hash_password, new_token, verify_password
from app.models.payment import utc_now
from app.models.user import User
from app.repositories.cart_repository import CartRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.privacy_repository import PrivacyRepository
from app.repositories.user_repository import SessionRepository, UserRepository
from app.schemas.user import ConsentsWrite
from app.services import user_service
from app.services.auth_service import throttle, user_read
from app.services.legal_service import TERMS_VERSION


def update_consents(db: Session, user: User, body: ConsentsWrite) -> dict:
    now = utc_now()
    if body.marketing_opt_in != user.marketing_opt_in:
        user.marketing_opt_in = body.marketing_opt_in
        user.marketing_updated_at = now
        security_event("privacy.marketing", user=user.id, enabled=body.marketing_opt_in)
    if body.accept_terms:
        user.terms_version = TERMS_VERSION
        user.terms_accepted_at = now
    db.commit()
    return user_read(user)


def _reauthenticate(db: Session, user: User, password: str) -> None:
    throttle(db, f"reauth:{user.id}", 10)
    if not verify_password(password, user.hashed_password):
        raise Unauthorized("Senha incorreta.")


def _account_orders(db: Session, user: User):
    link = CartRepository(db).link_for_user(user.id)
    return (OrderRepository(db).all_for_cart(link.cart_id) if link else []), link


def export_data(db: Session, user: User, password: str) -> dict:
    _reauthenticate(db, user, password)
    from app.services.return_service import return_read, return_for_order
    privacy = PrivacyRepository(db)
    orders, _ = _account_orders(db, user)
    data = {
        "generated_at": utc_now().isoformat(),
        "controller": get_settings().STORE_NAME,
        "account": {
            "email": user.email, "full_name": user.full_name, "phone": user.phone,
            "terms_version": user.terms_version,
            "terms_accepted_at": user.terms_accepted_at.isoformat() if user.terms_accepted_at else None,
            "marketing_opt_in": user.marketing_opt_in,
            "marketing_updated_at": user.marketing_updated_at.isoformat() if user.marketing_updated_at else None,
        },
        "addresses": user_service.list_addresses(db, user),
        "favorites": [{"product_id": pid, "name": name} for pid, name in privacy.favorites(user.id)],
        "reviews": [{"product_id": r.product_id, "rating": r.rating, "comment": r.comment,
                     "created_at": r.created_at.isoformat()} for r in privacy.reviews(user.id)],
        # O CPF aparece completo: é um dado da própria titular, entregue só a ela, após a senha.
        "orders": [{
            "id": o.id, "created_at": o.created_at.isoformat(), "status": o.status,
            "fulfillment_status": o.fulfillment_status, "items": o.items, "address": o.address,
            "payer_email": o.payer_email, "payer_document": o.payer_document,
            "subtotal_cents": o.subtotal_cents, "discount_cents": o.discount_cents,
            "shipping_cents": o.shipping_cents, "total_cents": o.total_cents,
            "return": (lambda r: return_read(r) if r else None)(return_for_order(db, o.id)),
        } for o in orders],
        "sessions": [{"device": s.device, "created_at": s.created_at.isoformat() if s.created_at else None,
                      "last_used_at": s.last_used_at.isoformat() if s.last_used_at else None}
                     for s in SessionRepository(db).list_for_user(user.id, utc_now())],
        "emails": [{"kind": n.kind, "status": n.status, "created_at": n.created_at.isoformat(),
                    "sent_at": n.sent_at.isoformat() if n.sent_at else None}
                   for n in privacy.notifications(user.id, {user.email, *(o.payer_email for o in orders)})],
    }
    db.commit()
    security_event("privacy.export", user=user.id)
    return data


def delete_account(db: Session, user: User, password: str) -> None:
    _reauthenticate(db, user, password)
    if user.is_admin:
        raise Conflict("Contas da administração são removidas pela gestão da loja, não por aqui.")
    UserRepository(db).lock(user.id)
    orders, link = _account_orders(db, user)
    if any(o.status == "awaiting_payment" for o in orders):
        raise Conflict("Há um pedido aguardando pagamento. Pague ou cancele antes de excluir a conta.")
    PrivacyRepository(db).erase_personal_data(user.id)
    if link:
        cart = CartRepository(db).get(link.cart_id)
        cart.items = []
        cart.version += 1
    user.email = f"excluida-{user.id}@anonimizado.invalid"
    user.hashed_password = hash_password(new_token(32))  # ninguém conhece esta senha
    user.full_name = user.phone = None
    user.marketing_opt_in = False
    user.unsubscribe_token_hash = None
    user.is_active = False
    user.deleted_at = utc_now()
    db.commit()
    security_event("privacy.account_deleted", user=user.id)


def unsubscribe_link(db: Session, user: User) -> str | None:
    """Gera (e troca) o link de descadastro de um clique. Sem API_PUBLIC_URL, o e-mail orienta pelo app."""
    base = get_settings().API_PUBLIC_URL.strip().rstrip("/")
    if not base:
        return None
    token = new_token(24)
    user.unsubscribe_token_hash = digest(token)
    return f"{base}/api/v1/unsubscribe?token={token}"


def unsubscribe(db: Session, token: str) -> bool:
    user = PrivacyRepository(db).by_unsubscribe_hash(digest(token))
    if user is None:
        return False
    user.marketing_opt_in = False
    user.marketing_updated_at = utc_now()
    user.unsubscribe_token_hash = None
    db.commit()
    security_event("privacy.unsubscribe", user=user.id)
    return True
