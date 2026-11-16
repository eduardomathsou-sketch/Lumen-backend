"""Fotos de produto guardadas no próprio banco (sem serviço de arquivos à parte).

O identificador é o SHA-256 do arquivo final: o endereço nunca muda de conteúdo (cache longo
no navegador e na CDN) e a mesma foto enviada duas vezes vira um registro só.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, deferred, mapped_column

from app.core.database import Base
from app.models.payment import utc_now


class MediaFile(Base):
    __tablename__ = "media_files"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_type: Mapped[str] = mapped_column(String(32))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(Integer)
    # Só carregado quando a foto é servida (listar não puxa os bytes).
    data: Mapped[bytes] = deferred(mapped_column(LargeBinary))
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now)
