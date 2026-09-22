import os
from typing import Literal
from functools import lru_cache
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Lumen Backend"
    DEBUG: bool = Field(default=False, validation_alias=AliasChoices("LUMEN_DEBUG", "DEBUG"))
    VERCEL: bool = False
    AUTO_CREATE_TABLES: bool | None = None
    SEED_CATALOG: bool | None = None
    DATABASE_URL: str = Field(default="sqlite:///./app.db", repr=False)
    DATABASE_URL_UNPOOLED: str = Field(default="", repr=False)
    CORS_ORIGINS: str = ""
    CORS_ALLOW_ORIGIN_REGEX: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    PAYMENT_WEBHOOK_SECRET: str = "development-webhook-secret"
    PAYMENT_PROVIDER: str = "sandbox"
    MERCADO_PAGO_ACCESS_TOKEN: str = Field(default="", repr=False)
    MERCADO_PAGO_WEBHOOK_SECRET: str = Field(default="", repr=False)
    MERCADO_PAGO_NOTIFICATION_URL: str = ""
    PAYMENT_ADMIN_TOKEN: str = Field(default="", repr=False)
    CRON_SECRET: str = Field(default="", repr=False)
    MAINTENANCE_MAX_ORDERS: int = Field(default=10, ge=1, le=100)
    SHIPPING_FLAT_RATE_CENTS: int | None = Field(default=None, ge=0, le=100000)
    SHIPPING_LABEL: str = "Entrega padrão"
    SHIPPING_DAYS: int = Field(default=7, ge=1, le=90)
    SHIPPING_PROVIDER: Literal['auto', 'flat', 'melhorenvio'] = 'auto'
    SHIPPING_ORIGIN_POSTAL_CODE: str = Field(default='59022080', pattern=r'^\d{8}$')
    MELHOR_ENVIO_TOKEN: str = Field(default='', repr=False)
    MELHOR_ENVIO_USER_AGENT: str = ''
    MELHOR_ENVIO_SANDBOX: bool = False
    ORDER_TTL_MINUTES: int = Field(default=30, ge=1, le=1440)

    @property
    def shipping_mode(self) -> str:
        if self.SHIPPING_PROVIDER != 'auto':
            return self.SHIPPING_PROVIDER
        return 'flat' if self.SHIPPING_FLAT_RATE_CENTS is not None else 'melhorenvio'

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
        populate_by_name=True,
    )

    @field_validator("DEBUG", mode="before")
    @classmethod
    def debug_mode(cls, value):
        # Some developer shells export DEBUG=release. Prefer LUMEN_DEBUG.
        return False if value == "release" else value

    @model_validator(mode="after")
    def deployment_defaults(self):
        if self.AUTO_CREATE_TABLES is None:
            self.AUTO_CREATE_TABLES = not self.VERCEL
        if self.SEED_CATALOG is None:
            self.SEED_CATALOG = not self.VERCEL
        if self.VERCEL:
            if not self.DATABASE_URL.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
                raise ValueError("Configure DATABASE_URL com a conexão PostgreSQL da Neon na Vercel.")
            if self.DEBUG or self.AUTO_CREATE_TABLES or self.SEED_CATALOG:
                raise ValueError("Na Vercel desative LUMEN_DEBUG, AUTO_CREATE_TABLES e SEED_CATALOG; use migrations.")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def cors_regex(self) -> str | None:
        return None if self.VERCEL else self.CORS_ALLOW_ORIGIN_REGEX or None


@lru_cache
def get_settings() -> Settings:
    # Deployment configuration comes exclusively from Vercel's environment.
    return Settings(_env_file=None if os.getenv("VERCEL") == "1" else ".env")
