from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db
from app.models.category import Category
from app.models.product import Product
from app.schemas.admin import CategoryWrite, ProductEdit, ProductWrite
from app.services.auth_service import current_admin

router = APIRouter(prefix='/admin', tags=['administration'], dependencies=[Depends(current_admin)])


def product_read(product):
    return {
        'id': product.id, 'name': product.name, 'description': product.description,
        'price_cents': int((Decimal(str(product.price)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)),
        'stock': product.stock, 'category_id': product.category_id,
        'category_name': product.category.name if product.category else None,
        'image_url': product.image_url, 'is_active': product.is_active, 'version': product.version,
        'weight_grams': product.weight_grams, 'height_cm': product.height_cm,
        'width_cm': product.width_cm, 'length_cm': product.length_cm,
    }


def values(body, db):
    if body.category_id is not None and db.get(Category, body.category_id) is None:
        raise HTTPException(422, 'Categoria não encontrada. Atualize a lista.')
    data = body.model_dump(mode='json', exclude={'version', 'price_cents'})
    data['price'] = body.price_cents / 100
    return data


@router.get('/products')
def products(search: str = Query(default='', max_length=150), is_active: bool | None = None,
             skip: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=100),
             db: Session = Depends(get_db)):
    statement = select(Product).options(selectinload(Product.category)).order_by(Product.id.desc())
    if search.strip():
        statement = statement.where(Product.name.icontains(search.strip(), autoescape=True))
    if is_active is not None:
        statement = statement.where(Product.is_active.is_(is_active))
    return [product_read(p) for p in db.scalars(statement.offset(skip).limit(limit))]


@router.get('/products/{product_id}')
def product(product_id: int, db: Session = Depends(get_db)):
    item = db.get(Product, product_id)
    if item is None:
        raise HTTPException(404, 'Produto não encontrado.')
    return product_read(item)


@router.post('/products', status_code=201)
def create_product(body: ProductWrite, db: Session = Depends(get_db)):
    item = Product(**values(body, db))
    db.add(item)
    db.commit()
    db.refresh(item)
    return product_read(item)


@router.put('/products/{product_id}')
def edit_product(product_id: int, body: ProductEdit, db: Session = Depends(get_db)):
    data = values(body, db)
    changed = db.execute(update(Product).where(Product.id == product_id, Product.version == body.version)
                         .values(**data, version=Product.version + 1)).rowcount
    if not changed:
        db.rollback()
        if db.get(Product, product_id) is None:
            raise HTTPException(404, 'Produto não encontrado.')
        raise HTTPException(409, 'O produto ou estoque mudou. Recarregue os dados antes de salvar.')
    db.commit()
    return product(product_id, db)


@router.get('/categories')
def categories(db: Session = Depends(get_db)):
    return [{'id': c.id, 'name': c.name, 'description': c.description}
            for c in db.scalars(select(Category).order_by(Category.name))]


@router.post('/categories', status_code=201)
def create_category(body: CategoryWrite, db: Session = Depends(get_db)):
    if db.scalar(select(Category.id).where(func.lower(Category.name) == body.name.lower())) is not None:
        raise HTTPException(409, 'Já existe uma categoria com esse nome.')
    item = Category(**body.model_dump())
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, 'Já existe uma categoria com esse nome.') from exc
    db.refresh(item)
    return {'id': item.id, 'name': item.name, 'description': item.description}
