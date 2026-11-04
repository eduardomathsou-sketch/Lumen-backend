from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_admin, get_db
from app.schemas.admin import CategoryWrite, ProductEdit, ProductWrite, VariantEdit, VariantWrite
from app.schemas.coupon import CouponEdit, CouponWrite
from app.schemas.order import FulfillmentWrite
from app.services import coupon_service, order_service
from app.services.product_service import ProductService
from app.utils.pagination import Page, page_params

# Todas as rotas exigem uma sessão ativa de conta com is_admin (conferido no banco).
router = APIRouter(prefix='/admin', tags=['administration'], dependencies=[Depends(current_admin)])


@router.get('/products')
def products(search: str = Query(default='', max_length=150), is_active: bool | None = None,
             page: Page = Depends(page_params), db: Session = Depends(get_db)):
    return ProductService(db).admin_search(page, search, is_active)


@router.get('/products/{product_id}')
def product(product_id: int, db: Session = Depends(get_db)):
    return ProductService(db).admin_get(product_id)


@router.post('/products', status_code=201)
def create_product(body: ProductWrite, db: Session = Depends(get_db)):
    return ProductService(db).create(body)


@router.put('/products/{product_id}')
def edit_product(product_id: int, body: ProductEdit, db: Session = Depends(get_db)):
    return ProductService(db).edit(product_id, body)


@router.get('/products/{product_id}/variants')
def variants(product_id: int, db: Session = Depends(get_db)):
    return ProductService(db).list_variants(product_id)


@router.post('/products/{product_id}/variants', status_code=201)
def create_variant(product_id: int, body: VariantWrite, db: Session = Depends(get_db)):
    return ProductService(db).create_variant(product_id, body)


@router.put('/variants/{variant_id}')
def edit_variant(variant_id: int, body: VariantEdit, db: Session = Depends(get_db)):
    return ProductService(db).edit_variant(variant_id, body)


@router.get('/categories')
def categories(db: Session = Depends(get_db)):
    return ProductService(db).list_categories()


@router.post('/categories', status_code=201)
def create_category(body: CategoryWrite, db: Session = Depends(get_db)):
    return ProductService(db).create_category(body)


# --- Cupons ---
@router.get('/coupons')
def coupons(db: Session = Depends(get_db)):
    return coupon_service.list_coupons(db)


@router.post('/coupons', status_code=201)
def create_coupon(body: CouponWrite, db: Session = Depends(get_db)):
    return coupon_service.create_coupon(db, body)


@router.put('/coupons/{coupon_id}')
def edit_coupon(coupon_id: int, body: CouponEdit, db: Session = Depends(get_db)):
    return coupon_service.edit_coupon(db, coupon_id, body)


# --- Pedidos e entrega ---
@router.get('/orders')
def orders(status: str | None = Query(default=None, max_length=30),
           fulfillment: str | None = Query(default=None, pattern=r'^(preparing|shipped|delivered)$'),
           page: Page = Depends(page_params), db: Session = Depends(get_db)):
    return order_service.admin_list(db, page, status, fulfillment)


@router.get('/orders/{order_id}')
def order(order_id: str, db: Session = Depends(get_db)):
    return order_service.admin_get(db, order_id)


@router.post('/orders/{order_id}/fulfillment')
def advance_fulfillment(order_id: str, body: FulfillmentWrite, db: Session = Depends(get_db)):
    return order_service.advance_fulfillment(db, order_id, body)
