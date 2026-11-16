from pydantic import BaseModel, ConfigDict, Field


class ReviewWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    rating: int = Field(strict=True, ge=1, le=5)
    comment: str = Field(default="", max_length=1000)
