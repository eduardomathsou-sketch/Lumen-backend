from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import SessionLocal, create_tables
from app.models.category import Category
from app.models.product import Product
from app.services.payment_service import PaymentProviderError, PaymentProviderConfigurationError

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    debug=settings.DEBUG,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.CORS_ALLOW_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Cart-Token", "Idempotency-Key"],
)


@app.exception_handler(PaymentProviderError)
async def payment_error(request: Request, exc: PaymentProviderError):
    if isinstance(exc, PaymentProviderConfigurationError):
        return JSONResponse(status_code=503, content={"detail": "Pagamento ainda não configurado pela loja."})
    return JSONResponse(status_code=502, content={"detail": "Não foi possível confirmar a operação. Retome o mesmo pedido para tentar novamente."})


@app.on_event("startup")
def startup_event() -> None:
    if settings.AUTO_CREATE_TABLES:
        create_tables()
    if settings.SEED_CATALOG:
        seed_database()


def seed_database() -> None:
    db = SessionLocal()
    try:
        existing_products = db.execute(select(Product.id)).first()
        if existing_products:
            return

        moda = Category(name="Moda feminina", description="Pecas selecionadas para a Lumen")
        beleza = Category(name="Beleza", description="Autocuidado e fragrancias")
        db.add_all([moda, beleza])
        db.commit()

        db.refresh(moda)
        db.refresh(beleza)

        products = [
            Product(
                name="Vestido Aura",
                description="Vestido de cetim champagne da colecao Vista Sua Essencia.",
                price=289.90,
                stock=12,
                category_id=moda.id,
                is_active=True,
            ),
            Product(
                name="Bolsa Aurora",
                description="Bolsa estruturada em tom dourado suave.",
                price=349.90,
                stock=8,
                category_id=moda.id,
                is_active=True,
            ),
            Product(
                name="Bruma Lunar",
                description="Bruma perfumada com notas florais e ambar.",
                price=89.90,
                stock=24,
                category_id=beleza.id,
                is_active=True,
            ),
            Product(
                name="Oleo Iluminar",
                description="Oleo corporal com brilho dourado sutil.",
                price=74.90,
                stock=16,
                category_id=beleza.id,
                is_active=True,
            ),
        ]

        db.add_all(products)
        db.commit()
    finally:
        db.close()


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": f"{settings.APP_NAME} is running"}


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": settings.APP_NAME, "version": app.version}


app.include_router(api_router)
