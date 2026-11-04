from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.api.deps import client_ip, current_user, get_db
from app.core.config import get_settings
from app.schemas.auth import Credentials
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["account"])


def limited(request: Request, body: Credentials, db: Session = Depends(get_db)):
    auth_service.throttle(db, f"ip:{client_ip(request)}", get_settings().AUTH_IP_LIMIT)
    auth_service.throttle(db, f"email:{body.email}", 10)


@router.post("/register", status_code=201, dependencies=[Depends(limited)])
def register(body: Credentials, x_cart_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    return auth_service.authenticate(db, body, x_cart_token, register=True)


@router.post("/login", dependencies=[Depends(limited)])
def login(body: Credentials, x_cart_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    return auth_service.authenticate(db, body, x_cart_token)


@router.get("/me")
def me(user=Depends(current_user)):
    return auth_service.user_read(user)


@router.post("/logout", status_code=204)
def logout(authorization: str = Header(), db: Session = Depends(get_db)):
    session, _ = auth_service.get_session(db, authorization)
    auth_service.logout(db, session)
