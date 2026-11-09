from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.api.deps import get_db

from app.api.v1.router import api_router
from app.api.maintenance import router as maintenance_router
from app.core.config import get_settings
from app.core.database import SessionLocal, create_tables
from app.core.exceptions import AppError
from app.core.http_security import SecurityHeadersMiddleware
from app.models import all as _all_models  # noqa: F401  (registra todas as tabelas)
from app.models.category import Category
from app.models.product import Product
from app.services.payment_service import PaymentProviderError, PaymentProviderConfigurationError

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Substitui o antigo @app.on_event("startup"), removido nas versões novas do Starlette.
    if settings.AUTO_CREATE_TABLES:
        create_tables()
    if settings.SEED_CATALOG:
        seed_database()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="0.4.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
    docs_url="/docs" if settings.EXPOSE_DOCS else None,
    redoc_url="/redoc" if settings.EXPOSE_DOCS else None,
    openapi_url="/openapi.json" if settings.EXPOSE_DOCS else None,
)

# Cabeçalhos de segurança em toda resposta (HSTS ligado na Vercel, que é sempre HTTPS).
app.add_middleware(SecurityHeadersMiddleware, hsts=settings.VERCEL)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_regex,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Cart-Token", "Idempotency-Key"],
)


@app.exception_handler(AppError)
async def app_error(request: Request, exc: AppError):
    # Erros de negócio lançados pelos services viram a resposta HTTP correspondente.
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)


@app.exception_handler(PaymentProviderError)
async def payment_error(request: Request, exc: PaymentProviderError):
    if isinstance(exc, PaymentProviderConfigurationError):
        return JSONResponse(status_code=503, content={"detail": "Pagamento ainda não configurado pela loja."})
    return JSONResponse(status_code=502, content={"detail": "Não foi possível confirmar a operação. Retome o mesmo pedido para tentar novamente."})


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Do not echo passwords, documents or request bodies in validation errors.
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]})


def seed_database() -> None:
    db = SessionLocal()
    try:
        existing_products = db.execute(select(Product.id)).first()
        if existing_products:
            return

        base = settings.SEED_IMAGE_BASE_URL.rstrip("/")
        moda = Category(name="Moda feminina", description="Peças selecionadas para a Lumen")
        beleza = Category(name="Beleza", description="Autocuidado e fragrâncias")
        db.add_all([moda, beleza])
        db.commit()

        db.refresh(moda)
        db.refresh(beleza)

        # Catálogo de demonstração. Composição e cuidados são ilustrativos: antes de vender,
        # troque pelos dados da etiqueta de cada peça (o CDC exige informação correta).
        products = [
            Product(
                name="Vestido Aura",
                description=("Cetim champagne de brilho discreto, que acompanha o movimento do corpo e "
                             "captura a luz a cada passo. Alças finas, decote suave e caimento fluido até o "
                             "tornozelo: uma peça para os momentos que pedem presença. Combina com sandália "
                             "de tiras fina e joias douradas delicadas. Coleção Vista sua essência."),
                composition="Cetim acetinado com leve elasticidade.",
                care=("Lavar à mão em água fria, do avesso. Não torcer. Secar à sombra, estendido. "
                      "Passar em temperatura baixa, pelo avesso."),
                price_cents=990,
                image_url=f"{base}/vestido-aura.png",
                stock=12,
                category_id=moda.id,
                is_active=True,
            ),
            Product(
                name="Bolsa Aurora",
                description=("Estrutura firme, linhas limpas e um dourado suave que ilumina sem excesso. "
                             "Alça de mão e alça transversal removível, para ir do dia à noite com a mesma "
                             "elegância. Espaço para o essencial: celular, carteira e um batom."),
                composition="Material sintético de toque macio; ferragens em tom dourado.",
                care="Guardar no saco de proteção, longe do sol. Limpar com pano macio e seco.",
                price_cents=750,
                image_url=f"{base}/bolsa-aurora.png",
                stock=8,
                category_id=moda.id,
                is_active=True,
            ),
            Product(
                name="Bruma Lunar",
                description=("Uma névoa leve de flores brancas sobre fundo de âmbar, que envolve a pele e os "
                             "cabelos e deixa um rastro delicado ao longo do dia. Para usar sozinha ou como "
                             "última camada do seu ritual."),
                composition="Notas: flores brancas, âmbar e almíscar.",
                care="Borrifar a cerca de 20 cm da pele ou dos cabelos. Manter longe do calor e da luz direta.",
                price_cents=250,
                image_url=f"{base}/bruma-lunar.png",
                stock=24,
                category_id=beleza.id,
                is_active=True,
            ),
            Product(
                name="Óleo Iluminar",
                description=("Textura seca, de absorção rápida, com partículas douradas sutis que deixam a "
                             "pele com brilho de fim de tarde. Nos ombros, no colo e nas pernas, antes de sair."),
                composition="Óleo corporal com pigmentos minerais de efeito iluminador.",
                care=("Aplicar na pele limpa e seca. Evitar contato com tecidos claros logo após a aplicação. "
                      "Uso externo."),
                price_cents=50,
                image_url=f"{base}/oleo-iluminar.png",
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


@app.get("/ready", tags=["health"])
def readiness(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1 FROM orders LIMIT 1"))
        db.execute(text("SELECT maintenance_checked_at FROM orders LIMIT 1"))
        db.execute(text("SELECT 1 FROM account_sessions LIMIT 1"))
        db.execute(text("SELECT is_admin FROM users LIMIT 1"))
        db.execute(text("SELECT image_url, version, price_cents FROM products LIMIT 1"))
        db.execute(text("SELECT weight_grams, height_cm, width_cm, length_cm FROM products LIMIT 1"))
        db.execute(text("SELECT shipping_details FROM orders LIMIT 1"))
        db.execute(text("SELECT id FROM shipping_quotes LIMIT 1"))
        db.execute(text("SELECT full_name, phone FROM users LIMIT 1"))
        db.execute(text("SELECT id FROM addresses LIMIT 1"))
        db.execute(text("SELECT id FROM product_variants LIMIT 1"))
        db.execute(text("SELECT id FROM coupons LIMIT 1"))
        db.execute(text("SELECT id FROM reviews LIMIT 1"))
        db.execute(text("SELECT discount_cents, fulfillment_status FROM orders LIMIT 1"))
        db.execute(text("SELECT terms_version, marketing_opt_in, deleted_at FROM users LIMIT 1"))
        db.execute(text("SELECT updated_at, reminded_at FROM carts LIMIT 1"))
        db.execute(text("SELECT composition, care FROM products LIMIT 1"))
        db.execute(text("SELECT id FROM notifications LIMIT 1"))
        db.execute(text("SELECT token_hash FROM password_resets LIMIT 1"))
        db.execute(text("SELECT id FROM return_requests LIMIT 1"))
        db.execute(text("SELECT public_id, device, last_used_at FROM account_sessions LIMIT 1"))
    except SQLAlchemyError:
        db.rollback()
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ready"}


app.include_router(api_router)
app.include_router(maintenance_router)
