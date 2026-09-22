from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ProductWrite(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    price_cents: int = Field(strict=True, gt=0, le=100_000_000)
    stock: int = Field(strict=True, ge=0, le=1_000_000)
    category_id: int | None = Field(default=None, gt=0)
    image_url: HttpUrl | None = None
    is_active: bool = True
    weight_grams: int = Field(default=500, strict=True, ge=1, le=30000)
    height_cm: int = Field(default=10, strict=True, ge=1, le=100)
    width_cm: int = Field(default=15, strict=True, ge=1, le=100)
    length_cm: int = Field(default=20, strict=True, ge=1, le=100)

    @field_validator('image_url')
    @classmethod
    def public_photo(cls, value):
        if value is not None and (value.scheme != 'https' or value.username or value.password or len(str(value)) > 2048):
            raise ValueError('Use um link HTTPS de imagem, sem credenciais, com até 2048 caracteres.')
        return value


class ProductEdit(ProductWrite):
    version: int = Field(strict=True, ge=0)


class CategoryWrite(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
