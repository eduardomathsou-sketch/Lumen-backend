from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_admin, get_db
from app.schemas.admin import CategoryWrite, ProductEdit, ProductWrite
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


@router.get('/categories')
def categories(db: Session = Depends(get_db)):
    return ProductService(db).list_categories()


@router.post('/categories', status_code=201)
def create_category(body: CategoryWrite, db: Session = Depends(get_db)):
    return ProductService(db).create_category(body)
