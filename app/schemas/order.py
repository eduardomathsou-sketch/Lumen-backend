from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.utils.validators import EMAIL_PATTERN, POSTAL_CODE_PATTERN, STATE_PATTERN, valid_document

__all__ = ["AddressWrite", "CheckoutWrite", "FulfillmentWrite", "valid_document"]


class AddressWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    recipient: str = Field(min_length=3, max_length=120)
    postal_code: str = Field(pattern=POSTAL_CODE_PATTERN)
    street: str = Field(min_length=3, max_length=150)
    number: str = Field(min_length=1, max_length=20)
    complement: str = Field(default="", max_length=100)
    district: str = Field(min_length=2, max_length=100)
    city: str = Field(min_length=2, max_length=100)
    state: str = Field(pattern=STATE_PATTERN)


class CheckoutWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    cart_version: int = Field(ge=0)
    expected_total_cents: int = Field(gt=0)
    payer_email: str = Field(max_length=255, pattern=EMAIL_PATTERN)
    payer_document: str = Field(pattern=r"^\d{11}(\d{3})?$")
    # Endereço digitado OU um endereço salvo da conta (address_id), nunca os dois.
    address: AddressWrite | None = None
    address_id: int | None = Field(default=None, gt=0)
    shipping_quote_id: str | None = Field(default=None, min_length=20, max_length=64)
    shipping_service_id: str | None = Field(default=None, pattern=r'^[12]$')
    coupon_code: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{3,30}$")

    @field_validator("payer_document")
    @classmethod
    def check_document(cls, value):
        if not valid_document(value):
            raise ValueError("CPF ou CNPJ inválido")
        return value

    @model_validator(mode="after")
    def one_address(self):
        if (self.address is None) == (self.address_id is None):
            raise ValueError("Informe o endereço ou escolha um endereço salvo.")
        return self


class FulfillmentWrite(BaseModel):
    """Admin avança a entrega: preparing -> shipped -> delivered."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    status: str = Field(pattern=r"^(shipped|delivered)$")
    tracking_code: str | None = Field(default=None, max_length=40)
