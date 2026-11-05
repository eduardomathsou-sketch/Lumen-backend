from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request
from sqlalchemy.orm import Session

from app.api.deps import client_ip, current_user, get_db
from app.core.config import get_settings
from app.schemas.auth import Credentials, PasswordResetConfirm, PasswordResetRequest, RegisterWrite
from app.services import auth_service, password_service

router = APIRouter(prefix="/auth", tags=["account"])


def limit(request: Request, db: Session, email: str) -> None:
    auth_service.throttle(db, f"ip:{client_ip(request)}", get_settings().AUTH_IP_LIMIT)
    auth_service.throttle(db, f"email:{email}", 10)


@router.post("/register", status_code=201)
def register(request: Request, body: RegisterWrite, x_cart_token: str | None = Header(default=None),
             db: Session = Depends(get_db)):
    limit(request, db, body.email)
    return auth_service.authenticate(db, body, x_cart_token, register=True)


@router.post("/login")
def login(request: Request, body: Credentials, x_cart_token: str | None = Header(default=None),
          db: Session = Depends(get_db)):
    limit(request, db, body.email)
    return auth_service.authenticate(db, body, x_cart_token)


@router.post("/password-reset", status_code=202)
def request_password_reset(request: Request, body: PasswordResetRequest, background: BackgroundTasks,
                           db: Session = Depends(get_db)):
    auth_service.throttle(db, f"ip:{client_ip(request)}", get_settings().AUTH_IP_LIMIT)
    auth_service.throttle(db, f"reset:{body.email}", 5)
    password_service.request_reset(db, body.email, background)
    # Mesma resposta com ou sem conta: não revela quais e-mails estão cadastrados.
    return {"detail": "Se houver uma conta com este e-mail, enviamos as instruções para criar uma nova senha."}


@router.post("/password-reset/confirm", status_code=204)
def confirm_password_reset(request: Request, body: PasswordResetConfirm, db: Session = Depends(get_db)):
    auth_service.throttle(db, f"ip:{client_ip(request)}", get_settings().AUTH_IP_LIMIT)
    password_service.confirm_reset(db, body)


@router.get("/me")
def me(user=Depends(current_user)):
    return auth_service.user_read(user)


@router.post("/logout", status_code=204)
def logout(authorization: str = Header(), db: Session = Depends(get_db)):
    session, _ = auth_service.get_session(db, authorization)
    auth_service.logout(db, session)
