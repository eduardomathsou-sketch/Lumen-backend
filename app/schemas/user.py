from pydantic import BaseModel, ConfigDict, Field

from app.utils.validators import POSTAL_CODE_PATTERN, STATE_PATTERN


class ProfileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    full_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, pattern=r"^\d{10,11}$")  # DDD + número, só dígitos


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class AddressSave(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    label: str = Field(default="Casa", min_length=1, max_length=40)
    recipient: str = Field(min_length=3, max_length=120)
    postal_code: str = Field(pattern=POSTAL_CODE_PATTERN)
    street: str = Field(min_length=3, max_length=150)
    number: str = Field(min_length=1, max_length=20)
    complement: str = Field(default="", max_length=100)
    district: str = Field(min_length=2, max_length=100)
    city: str = Field(min_length=2, max_length=100)
    state: str = Field(pattern=STATE_PATTERN)
    is_default: bool = False


class ConsentsWrite(BaseModel):
    """Preferências de privacidade: marketing liga/desliga; accept_terms renova o aceite."""
    model_config = ConfigDict(extra="forbid")
    marketing_opt_in: bool
    accept_terms: bool = False


class PasswordConfirm(BaseModel):
    """Reautenticação para ações sensíveis (baixar dados, excluir conta)."""
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=128)
