from pydantic import BaseModel, ConfigDict, Field, field_validator


def valid_document(value: str) -> bool:
    if not value.isdigit() or len(set(value)) == 1 or len(value) not in (11, 14):
        return False
    digits = [int(x) for x in value]
    if len(digits) == 11:
        for size in (9, 10):
            check = (sum(digits[i] * (size + 1 - i) for i in range(size)) * 10) % 11
            if digits[size] != (0 if check == 10 else check):
                return False
    else:
        for size, weights in ((12, [5,4,3,2,9,8,7,6,5,4,3,2]), (13, [6,5,4,3,2,9,8,7,6,5,4,3,2])):
            remainder = sum(a * b for a, b in zip(digits[:size], weights)) % 11
            if digits[size] != (0 if remainder < 2 else 11 - remainder):
                return False
    return True


class AddressWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    recipient: str = Field(min_length=3, max_length=120)
    postal_code: str = Field(pattern=r"^\d{8}$")
    street: str = Field(min_length=3, max_length=150)
    number: str = Field(min_length=1, max_length=20)
    complement: str = Field(default="", max_length=100)
    district: str = Field(min_length=2, max_length=100)
    city: str = Field(min_length=2, max_length=100)
    state: str = Field(pattern=r"^(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)$")


class CheckoutWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    cart_version: int = Field(ge=0)
    expected_total_cents: int = Field(gt=0)
    payer_email: str = Field(max_length=255, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    payer_document: str = Field(pattern=r"^\d{11}(\d{3})?$")
    address: AddressWrite

    @field_validator("payer_document")
    @classmethod
    def check_document(cls, value):
        if not valid_document(value):
            raise ValueError("CPF ou CNPJ inválido")
        return value
