from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

BADGES = ('novidade', 'pronta_entrega', 'edicao_limitada', 'ultimas_pecas')


class ProductWrite(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    composition: str | None = Field(default=None, max_length=200)
    care: str | None = Field(default=None, max_length=300)
    price_cents: int = Field(strict=True, gt=0, le=100_000_000)
    compare_at_cents: int | None = Field(default=None, strict=True, gt=0, le=100_000_000)
    badge: Literal[BADGES] | None = None
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


    @model_validator(mode='after')
    def honest_discount(self):
        if self.compare_at_cents is not None and self.compare_at_cents <= self.price_cents:
            raise ValueError('O preço "de" precisa ser maior que o preço atual (ou deixe em branco).')
        return self


class ProductEdit(ProductWrite):
    version: int = Field(strict=True, ge=0)


class CategoryWrite(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)


class VariantWrite(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    size: str = Field(default='', max_length=20)
    color: str = Field(default='', max_length=40)
    stock: int = Field(strict=True, ge=0, le=1_000_000)
    is_active: bool = True

    @field_validator('color')
    @classmethod
    def size_or_color(cls, value, info):
        if not value and not info.data.get('size'):
            raise ValueError('Informe o tamanho, a cor ou os dois.')
        return value


class VariantEdit(VariantWrite):
    version: int = Field(strict=True, ge=0)
