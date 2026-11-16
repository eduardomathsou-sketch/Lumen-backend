"""Envio de fotos pela administração.

A foto recebida nunca é guardada como veio:
1. só JPG, PNG ou WebP, até 4 MB (limite de corpo da Vercel é 4,5 MB);
2. o Pillow abre com teto de pixels (contra "bombas" de descompressão);
3. a orientação da câmera é aplicada e a foto é regravada em JPEG, no máximo 1600 px,
   SEM os metadados (EXIF pode trazer a localização GPS de onde a foto foi tirada);
4. transparência vira fundo branco.
"""
import hashlib
import warnings
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppError, NotFound, Unprocessable
from app.models.media import MediaFile

MAX_UPLOAD_BYTES = 4 * 1024 * 1024
MAX_SIDE = 1600
MIN_SIDE = 200
MAX_PIXELS = 40_000_000
ACCEPTED = {"image/jpeg": "JPEG", "image/jpg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
FORMATS = ("JPEG", "PNG", "WEBP")
UNREADABLE = "Não consegui abrir essa foto. Envie um arquivo JPG, PNG ou WebP."

Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class PayloadTooLarge(AppError):
    status_code = 413


def too_large() -> PayloadTooLarge:
    return PayloadTooLarge("Foto grande demais: envie até 4 MB.")


def check_content_type(content_type: str | None) -> None:
    if (content_type or "").split(";")[0].strip().lower() not in ACCEPTED:
        raise Unprocessable("Envie uma foto JPG, PNG ou WebP.")


def prepare(raw: bytes) -> tuple[bytes, int, int]:
    if not raw:
        raise Unprocessable("Nenhuma foto recebida.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise too_large()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(BytesIO(raw), formats=FORMATS)
            image.load()
            image = ImageOps.exif_transpose(image)
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning,
            OSError, ValueError, SyntaxError, EOFError) as exc:
        raise Unprocessable(UNREADABLE) from exc
    if min(image.size) < MIN_SIDE:
        raise Unprocessable(f"Foto pequena demais: use pelo menos {MIN_SIDE} × {MIN_SIDE} pixels.")
    if image.mode in ("RGBA", "LA", "P", "PA"):
        rgba = image.convert("RGBA")
        image = Image.new("RGB", rgba.size, (255, 255, 255))
        image.paste(rgba, mask=rgba.getchannel("A"))
    else:
        image = image.convert("RGB")
    image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    out = BytesIO()
    # Sem exif=..., o arquivo final não carrega metadado nenhum da câmera.
    image.save(out, "JPEG", quality=85, optimize=True, progressive=True)
    return out.getvalue(), image.width, image.height


def public_url(media_id: str, base_url: str) -> str:
    base = (get_settings().API_PUBLIC_URL.strip() or base_url).rstrip("/")
    return f"{base}/api/v1/media/{media_id}.jpg"


def store(db: Session, raw: bytes, uploaded_by: int | None, base_url: str) -> dict:
    data, width, height = prepare(raw)
    media_id = hashlib.sha256(data).hexdigest()
    if db.get(MediaFile, media_id) is None:
        db.add(MediaFile(id=media_id, content_type="image/jpeg", width=width, height=height,
                         size_bytes=len(data), data=data, uploaded_by=uploaded_by))
        db.commit()
    return {"id": media_id, "url": public_url(media_id, base_url), "width": width, "height": height,
            "size_bytes": len(data)}


def load(db: Session, media_id: str) -> MediaFile:
    media = db.get(MediaFile, media_id)
    if media is None:
        raise NotFound("Foto não encontrada.")
    return media
