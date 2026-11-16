"""Acesso a dados dos cupons."""
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models.coupon import Coupon


class CouponRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, coupon_id: int) -> Coupon | None:
        return self.db.get(Coupon, coupon_id)

    def by_code(self, code: str) -> Coupon | None:
        return self.db.scalar(select(Coupon).where(Coupon.code == code))

    def list_all(self) -> list[Coupon]:
        return list(self.db.scalars(select(Coupon).order_by(Coupon.id.desc())))

    def add(self, coupon: Coupon) -> Coupon:
        self.db.add(coupon)
        self.db.flush()
        return coupon

    def update_if_version(self, coupon_id: int, version: int, values: dict) -> bool:
        result = self.db.execute(update(Coupon).where(Coupon.id == coupon_id, Coupon.version == version)
                                 .values(**values, version=Coupon.version + 1))
        return result.rowcount == 1

    def use(self, code: str) -> bool:
        """Reserva um uso numa instrução atômica: dois pedidos não passam do limite."""
        result = self.db.execute(update(Coupon).where(
            Coupon.code == code, Coupon.is_active.is_(True),
            or_(Coupon.max_uses.is_(None), Coupon.used_count < Coupon.max_uses),
        ).values(used_count=Coupon.used_count + 1))
        return result.rowcount == 1

    def release(self, code: str) -> None:
        self.db.execute(update(Coupon).where(Coupon.code == code, Coupon.used_count > 0)
                        .values(used_count=Coupon.used_count - 1))
