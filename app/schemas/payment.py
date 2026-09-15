from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


PaymentMethod = Literal["pix", "card"]
PaymentStatus = Literal["pending", "paid", "failed", "cancelled", "refunded"]


class ChargeCreate(BaseModel):
    """Only provider tokens are accepted for cards; never send card numbers or CVVs."""

    model_config = ConfigDict(extra="forbid")

    order_reference: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    method: PaymentMethod
    currency: Literal["BRL"] = "BRL"
    card_token: str | None = Field(default=None, min_length=8, max_length=255)
    payer_email: str | None = Field(default=None, min_length=5, max_length=255)
    payer_document: str | None = Field(default=None, min_length=11, max_length=14, pattern=r"^\d+$")

    @model_validator(mode="after")
    def validate_card_token(self):
        if self.method == "card" and not self.card_token:
            raise ValueError("card_token is required for card payments")
        return self


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_reference: str
    amount: Decimal
    currency: str
    method: str
    status: str
    provider: str
    provider_charge_id: str
    next_action: dict | None = None
    paid_at: datetime | None
    created_at: datetime


class WebhookData(BaseModel):
    provider_charge_id: str = Field(min_length=1, max_length=100)
    status: PaymentStatus


class ProviderWebhook(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=60)
    data: WebhookData


class WebhookResult(BaseModel):
    status: Literal["processed", "duplicate"]
    payment: PaymentRead


class ReconciliationItem(BaseModel):
    payment_id: int
    provider_charge_id: str
    status: str
    result: Literal["ok", "needs_attention"]
    reason: str | None = None


class ReconciliationResult(BaseModel):
    checked: int
    needs_attention: int
    payments: list[ReconciliationItem]
