from fastapi import APIRouter
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.catalog import router as catalog_router
from app.api.v1.endpoints.commerce import router as commerce_router

from app.api.v1.endpoints.payments import router as payments_router
from app.api.v1.endpoints.products import router as products_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/api/v1")
api_router.include_router(catalog_router, prefix="/api/v1")
api_router.include_router(commerce_router, prefix="/api/v1")
api_router.include_router(products_router, prefix="/api/v1")
api_router.include_router(payments_router, prefix="/api/v1")
