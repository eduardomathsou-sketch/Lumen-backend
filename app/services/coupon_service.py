"""Regras de cupom: validade, compra mínima, limite de usos e cálculo do desconto."""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound, Unprocessable
from app.models.coupon import Coupon
from app.models.payment import as_utc, utc_now
from app.repositories.coupon_repository import CouponRepository
from app.schemas.coupon import CouponEdit, CouponWrite


def normalize(code: str | None) -> str | None:
    return code.strip().upper() if code and code.strip() else None


def money(cents: int) -> str:
    return f"R$ {cents / 100:.2f}".replace(".", ",")


def discount_for(coupon: Coupon, subtotal_cents: int) -> int:
    if coupon.kind == "percent":
        # Arredonda para baixo: o desconto nunca passa do percentual anunciado.
        discount = subtotal_cents * coupon.value // 100
    else:
        discount = coupon.value
    # O total dos produtos nunca chega a zero (o PIX não aceita R$ 0,00).
    return max(0, min(discount, subtotal_cents - 1))


def evaluate(db: Session, code: str | None, subtotal_cents: int) -> tuple[Coupon | None, int]:
    code = normalize(code)
    if code is None:
        return None, 0
    coupon = CouponRepository(db).by_code(code)
    if coupon is None or not coupon.is_active:
        raise Unprocessable("Cupom inválido.")
    if coupon.expires_at is not None and as_utc(coupon.expires_at) <= utc_now():
        raise Unprocessable("Este cupom expirou.")
    if coupon.max_uses is not None and coupon.used_count >= coupon.max_uses:
        raise Unprocessable("Este cupom esgotou.")
    if subtotal_cents < coupon.min_subtotal_cents:
        raise Unprocessable(f"Este cupom vale para compras a partir de {money(coupon.min_subtotal_cents)}.")
    return coupon, discount_for(coupon, subtotal_cents)


def reserve_use(db: Session, code: str) -> None:
    if not CouponRepository(db).use(code):
        raise Conflict("Este cupom acabou de esgotar. Revise a sacola.")


def release_use(db: Session, code: str) -> None:
    CouponRepository(db).release(code)


# --- Administração ---
def coupon_read(coupon: Coupon) -> dict:
    return {"id": coupon.id, "code": coupon.code, "kind": coupon.kind, "value": coupon.value,
            "min_subtotal_cents": coupon.min_subtotal_cents, "expires_at": coupon.expires_at,
            "max_uses": coupon.max_uses, "used_count": coupon.used_count, "is_active": coupon.is_active,
            "version": coupon.version}


def list_coupons(db: Session) -> list[dict]:
    return [coupon_read(c) for c in CouponRepository(db).list_all()]


def create_coupon(db: Session, body: CouponWrite) -> dict:
    try:
        coupon = CouponRepository(db).add(Coupon(**body.model_dump()))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("Já existe um cupom com esse código.") from exc
    return coupon_read(coupon)


def edit_coupon(db: Session, coupon_id: int, body: CouponEdit) -> dict:
    coupons = CouponRepository(db)
    try:
        changed = coupons.update_if_version(coupon_id, body.version, body.model_dump(exclude={"version"}))
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("Já existe um cupom com esse código.") from exc
    if not changed:
        db.rollback()
        if coupons.get(coupon_id) is None:
            raise NotFound("Cupom não encontrado.")
        raise Conflict("O cupom mudou. Recarregue os dados antes de salvar.")
    db.commit()
    coupon = coupons.get(coupon_id)
    db.refresh(coupon)
    return coupon_read(coupon)
