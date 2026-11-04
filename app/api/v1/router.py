from fastapi import APIRouter

from app.api.v1.endpoints import admin, auth, cart, categories, favorites, orders, payments, products, users

api_router = APIRouter(prefix="/api/v1")
for module in (auth, users, products, categories, favorites, cart, orders, payments, admin):
    api_router.include_router(module.router)
