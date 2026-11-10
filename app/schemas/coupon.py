from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

COUPON_CODE = r"^[A-Za-z0-9_-]{3,30}$"


class CouponWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    code: str = Field(pattern=COUPON_CODE)
    kind: Literal["percent", "fixed"]
    value: int = Field(strict=True, gt=0, le=100_000_00)
    min_subtotal_cents: int = Field(default=0, strict=True, ge=0, le=100_000_00)
    expires_at: datetime | None = None
    max_uses: int | None = Field(default=None, strict=True, ge=1, le=1_000_000)
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def upper(cls, value):
        return value.upper()

    @model_validator(mode="after")
    def coherent(self):
        if self.kind == "percent" and self.value > 90:
            raise ValueError("Desconto percentual vai de 1% a 90%.")
        # Garante total maior que zero: o PIX não aceita cobrança de R$ 0,00.
        if self.kind == "fixed" and self.min_subtotal_cents <= self.value:
            raise ValueError("Cupom de valor fixo precisa de compra mínima maior que o desconto.")
        return self


class CouponEdit(CouponWrite):
    version: int = Field(strict=True, ge=0)
