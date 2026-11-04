from fastapi import APIRouter

from app.api.v1.endpoints import admin, auth, cart, categories, favorites, orders, payments, products

api_router = APIRouter(prefix="/api/v1")
for module in (auth, products, categories, favorites, cart, orders, payments, admin):
    api_router.include_router(module.router)
