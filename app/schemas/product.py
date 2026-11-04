from pydantic import BaseModel, ConfigDict


class ProductRead(BaseModel):
    """Produto como a vitrine pública mostra.

    `price` (reais) é mantido para o app atual; `price_cents` é o valor exato.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    price: float
    price_cents: int
    stock: int
    category_id: int | None = None
    category_name: str | None = None
    image_url: str | None = None
    is_active: bool = True
