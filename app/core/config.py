import os
from typing import Literal
from functools import lru_cache
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Segredos de produção precisam ter pelo menos este tamanho (ex.: secrets.token_urlsafe(32)).
MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    APP_NAME: str = "Lumen Backend"
    DEBUG: bool = Field(default=False, validation_alias=AliasChoices("LUMEN_DEBUG", "DEBUG"))
    VERCEL: bool = False
    AUTO_CREATE_TABLES: bool | None = None
    SEED_CATALOG: bool | None = None
    # Documentação interativa (/docs). Fica ligada no desenvolvimento e desligada na Vercel,
    # a menos que seja pedida explicitamente (ex.: no dia da apresentação).
    EXPOSE_DOCS: bool | None = None
    DATABASE_URL: str = Field(default="sqlite:///./app.db", repr=False)
    DATABASE_URL_UNPOOLED: str = Field(default="", repr=False)
    CORS_ORIGINS: str = ""
    CORS_ALLOW_ORIGIN_REGEX: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    # Cabeçalho com o IP real da cliente quando a API roda atrás de um proxy confiável.
    # Na Vercel o padrão é x-real-ip, que a própria Vercel preenche e sobrescreve.
    CLIENT_IP_HEADER: str = ""
    # Sem valor padrão de propósito: sem segredo configurado, o webhook do sandbox fica desligado.
    PAYMENT_WEBHOOK_SECRET: str = Field(default="", repr=False)
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
    # Limites por IP em 15 minutos. Uma sala de aula costuma sair por um único IP (rede da
    # faculdade), por isso o limite por IP é folgado; o limite por e-mail (10) segura força bruta.
    AUTH_IP_LIMIT: int = Field(default=100, ge=10, le=10000)
    # Validade do código de acesso (sessão). A da administração é curta de propósito: é a
    # conta que mais vale a pena roubar (muda preço, vê pedidos e endereços).
    SESSION_DAYS: int = Field(default=7, ge=1, le=30)
    ADMIN_SESSION_HOURS: int = Field(default=12, ge=1, le=168)
    MAX_SESSIONS_PER_USER: int = Field(default=10, ge=1, le=50)
    CART_IP_LIMIT: int = Field(default=120, ge=10, le=10000)
    # Contra "sequestro de estoque": um robô criando pedidos sem pagar prenderia as peças por
    # ORDER_TTL_MINUTES. Limita pedidos novos por IP (15 min) e unidades de cada produto por pedido.
    ORDER_IP_LIMIT: int = Field(default=30, ge=5, le=10000)
    MAX_UNITS_PER_ITEM: int = Field(default=10, ge=1, le=99)
    # Contra o chute de códigos de cupom: códigos inexistentes por IP em 15 minutos.
    COUPON_ATTEMPT_LIMIT: int = Field(default=10, ge=3, le=1000)
    # Onde estão as fotos do catálogo de demonstração (pasta /products do site Flutter publicado).
    SEED_IMAGE_BASE_URL: str = "https://lumen-flutter-blond.vercel.app/products"

    # Identificação da loja exigida pelo Decreto 7.962/2013 (aparece nas políticas e nos e-mails).
    STORE_NAME: str = "Lumen"
    STORE_LEGAL_NAME: str = ""
    STORE_DOCUMENT: str = ""
    STORE_ADDRESS: str = ""
    STORE_CONTACT_EMAIL: str = ""
    # Encarregado de dados (LGPD, art. 41). Sem valor, usa o e-mail de atendimento.
    DPO_EMAIL: str = ""
    # Endereço público da API (link de descadastro) e da tela de nova senha no app.
    # O link de senha aceita {token}; sem ele, o e-mail traz o código para colar no app.
    API_PUBLIC_URL: str = ""
    PASSWORD_RESET_URL: str = ""

    # E-mails: "console" (desenvolvimento), "smtp" (produção) ou "memory" (testes).
    EMAIL_PROVIDER: Literal["console", "smtp", "memory"] = "console"
    EMAIL_FROM: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = Field(default=587, ge=1, le=65535)
    SMTP_USERNAME: str = Field(default="", repr=False)
    SMTP_PASSWORD: str = Field(default="", repr=False)
    # 465 usa SSL direto; as outras portas, STARTTLS.
    SMTP_TIMEOUT_SECONDS: int = Field(default=10, ge=1, le=60)
    # Lembrete de sacola só para contas que aceitaram comunicações; 0 desliga.
    CART_REMINDER_HOURS: int = Field(default=24, ge=0, le=168)

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
        if self.EXPOSE_DOCS is None:
            self.EXPOSE_DOCS = not self.VERCEL
        if self.VERCEL and not self.CLIENT_IP_HEADER:
            self.CLIENT_IP_HEADER = "x-real-ip"
        if self.VERCEL:
            if not self.DATABASE_URL.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
                raise ValueError("Configure DATABASE_URL com a conexão PostgreSQL da Neon na Vercel.")
            if self.DEBUG or self.AUTO_CREATE_TABLES or self.SEED_CATALOG:
                raise ValueError("Na Vercel desative LUMEN_DEBUG, AUTO_CREATE_TABLES e SEED_CATALOG; use migrations.")
            # Um segredo curto ou conhecido permitiria forjar avisos de pagamento.
            if self.PAYMENT_PROVIDER.lower() == "sandbox" and len(self.PAYMENT_WEBHOOK_SECRET) < MIN_SECRET_LENGTH:
                raise ValueError("Na Vercel, o sandbox exige PAYMENT_WEBHOOK_SECRET com 32+ caracteres aleatórios.")
            for name in ("CRON_SECRET", "PAYMENT_ADMIN_TOKEN"):
                value = getattr(self, name)
                if value and len(value) < MIN_SECRET_LENGTH:
                    raise ValueError(f"{name} precisa ter 32+ caracteres aleatórios.")
            if self.EMAIL_PROVIDER == "memory":
                raise ValueError("EMAIL_PROVIDER=memory é só para testes.")
        if self.EMAIL_PROVIDER == "smtp" and not (self.SMTP_HOST and self.EMAIL_FROM):
            raise ValueError("Para enviar e-mails por SMTP, configure SMTP_HOST e EMAIL_FROM.")
        return self

    @property
    def contact_email(self) -> str:
        return self.STORE_CONTACT_EMAIL.strip()

    @property
    def dpo_email(self) -> str:
        return self.DPO_EMAIL.strip() or self.contact_email

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
