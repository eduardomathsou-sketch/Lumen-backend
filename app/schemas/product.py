from pydantic import BaseModel, ConfigDict


class VariantRead(BaseModel):
    id: int
    size: str
    color: str
    label: str
    stock: int


class ProductRead(BaseModel):
    """Produto como a vitrine pública mostra.

    `price` (reais) é mantido para o app atual; `price_cents` é o valor exato.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    composition: str | None = None
    care: str | None = None
    price: float
    price_cents: int
    stock: int
    category_id: int | None = None
    category_name: str | None = None
    image_url: str | None = None
    is_active: bool = True
    # Vazia para produtos sem tamanho/cor; quando existe, a compra exige escolher uma.
    variants: list[VariantRead] = []
    rating_average: float | None = None
    rating_count: int = 0
