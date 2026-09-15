from pydantic import BaseModel, ConfigDict, Field


class CartItemWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity: int = Field(ge=0, le=99)
    version: int = Field(ge=0)
