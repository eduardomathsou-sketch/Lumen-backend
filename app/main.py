from fastapi import FastAPI
from sqlalchemy import select

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import SessionLocal, create_tables
from app.models.category import Category
from app.models.product import Product

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    debug=settings.DEBUG,
)


@app.on_event("startup")
def startup_event() -> None:
    create_tables()
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


app.include_router(api_router)
