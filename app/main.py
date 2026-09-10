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

        eletronicos = Category(name="Eletronicos", description="Produtos tecnologicos")
        casa = Category(name="Casa", description="Itens para casa e organizacao")
        db.add_all([eletronicos, casa])
        db.commit()

        db.refresh(eletronicos)
        db.refresh(casa)

        products = [
            Product(
                name="Notebook Pro 14",
                description="Notebook leve com desempenho para trabalho e estudo.",
                price=4999.90,
                stock=10,
                category_id=eletronicos.id,
                is_active=True,
            ),
            Product(
                name="Smartphone X10",
                description="Celular com camera de alta qualidade e bateria longa.",
                price=2499.00,
                stock=18,
                category_id=eletronicos.id,
                is_active=True,
            ),
            Product(
                name="Cafeteira Deluxe",
                description="Cafeteira com preparo rapido e design moderno.",
                price=399.00,
                stock=22,
                category_id=casa.id,
                is_active=True,
            ),
            Product(
                name="Ventilador Silencioso",
                description="Ventilador compacto para ambientes menores.",
                price=189.90,
                stock=14,
                category_id=casa.id,
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
