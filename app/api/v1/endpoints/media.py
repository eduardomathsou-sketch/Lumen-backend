"""Fotos de produto: envio (só administração) e entrega pública com cache longo."""
import re

from fastapi import APIRouter, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.api.deps import current_admin, get_db
from app.core.exceptions import NotFound
from app.models.user import User
from app.services import media_service

router = APIRouter(tags=["media"])
MEDIA_NAME = re.compile(r"^([0-9a-f]{64})\.jpg$")
IMMUTABLE = "public, max-age=31536000, s-maxage=31536000, immutable"


@router.post("/admin/media", status_code=201)
async def upload(request: Request, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    media_service.check_content_type(request.headers.get("content-type"))
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > media_service.MAX_UPLOAD_BYTES:
        raise media_service.too_large()
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > media_service.MAX_UPLOAD_BYTES:
            raise media_service.too_large()
    # Pillow e banco são síncronos: fora do laço de eventos.
    return await run_in_threadpool(media_service.store, db, bytes(raw), admin.id, str(request.base_url))


@router.get("/media/{name}")
def serve(name: str, db: Session = Depends(get_db)):
    match = MEDIA_NAME.fullmatch(name)
    if not match:
        raise NotFound("Foto não encontrada.")
    media = media_service.load(db, match.group(1))
    return Response(content=media.data, media_type=media.content_type, headers={
        "Cache-Control": IMMUTABLE,
        "ETag": f'"{media.id}"',
        # A loja (outro domínio) precisa poder exibir a foto; nada além disso.
        "Cross-Origin-Resource-Policy": "cross-origin",
        "Content-Security-Policy": "default-src 'none'; sandbox",
    })
