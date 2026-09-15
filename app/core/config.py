from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Lumen Backend"
    DEBUG: bool = False
    AUTO_CREATE_TABLES: bool = True
    SEED_CATALOG: bool = True
    DATABASE_URL: str = "sqlite:///./app.db"
    CORS_ORIGINS: str = ""
    CORS_ALLOW_ORIGIN_REGEX: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    PAYMENT_WEBHOOK_SECRET: str = "development-webhook-secret"
    PAYMENT_PROVIDER: str = "sandbox"
    MERCADO_PAGO_ACCESS_TOKEN: str = ""
    MERCADO_PAGO_WEBHOOK_SECRET: str = ""
    MERCADO_PAGO_NOTIFICATION_URL: str = ""
    PAYMENT_ADMIN_TOKEN: str = ""
    SHIPPING_FLAT_RATE_CENTS: int | None = Field(default=None, ge=0, le=100000)
    SHIPPING_LABEL: str = "Entrega padrão"
    SHIPPING_DAYS: int = Field(default=7, ge=1, le=90)
    ORDER_TTL_MINUTES: int = Field(default=30, ge=1, le=1440)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
