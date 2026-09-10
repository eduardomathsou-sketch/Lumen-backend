from pydantic import BaseModel, ConfigDict, Field


class ProductBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    description: str | None = None
    price: float = Field(..., gt=0)
    stock: int = Field(default=0, ge=0)
    category_id: int | None = None
    is_active: bool = True


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    price: float | None = Field(default=None, gt=0)
    stock: int | None = Field(default=None, ge=0)
    category_id: int | None = None
    is_active: bool | None = None


class ProductRead(ProductBase):
    id: int
    category_name: str | None = None

    model_config = ConfigDict(from_attributes=True)
