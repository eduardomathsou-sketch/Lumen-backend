from pydantic import BaseModel, ConfigDict, Field, field_validator


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=255, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class RegisterWrite(Credentials):
    """Cadastro com aceite explícito (click-wrap) e consentimento de marketing separado."""
    accept_terms: bool
    marketing_opt_in: bool = False

    @field_validator("accept_terms")
    @classmethod
    def must_accept(cls, value):
        if value is not True:
            raise ValueError("Para criar a conta, aceite os Termos de Uso e a Política de Privacidade.")
        return value


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=255, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

    @field_validator("email", mode="before")
    @classmethod
    def normalize(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class PasswordResetConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=100)
    new_password: str = Field(min_length=12, max_length=128)
