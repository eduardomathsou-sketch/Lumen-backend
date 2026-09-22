import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.maintenance import run_batch

router = APIRouter()


def require_cron(authorization: str | None = Header(default=None)):
    secret = get_settings().CRON_SECRET
    if not secret or not hmac.compare_digest((authorization or "").encode(), f"Bearer {secret}".encode()):
        raise HTTPException(401, "Autorização necessária.")


@router.get("/api/internal/maintenance", dependencies=[Depends(require_cron)], include_in_schema=False)
def maintenance():
    result = run_batch()
    return JSONResponse(result, status_code=503 if result["failed"] else 200,
                        headers={"Cache-Control": "no-store"})
