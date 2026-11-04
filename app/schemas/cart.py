from pydantic import BaseModel, ConfigDict, Field


class CartItemWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity: int = Field(ge=0, le=99)
    version: int = Field(ge=0)
    # Obrigatório quando o produto tem variações (tamanho/cor).
    variant_id: int | None = Field(default=None, gt=0)
