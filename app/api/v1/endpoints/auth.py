from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.schemas.auth import Credentials
from app.services.auth_service import authenticate, throttle, current_user, user_read, get_session

router = APIRouter(prefix="/auth", tags=["account"])


def limited(request: Request, body: Credentials, db: Session = Depends(get_db)):
    throttle(db, f"ip:{request.client.host if request.client else 'unknown'}", 50)
    throttle(db, f"email:{body.email}", 10)


@router.post("/register", status_code=201, dependencies=[Depends(limited)])
def register(body: Credentials, x_cart_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    return authenticate(db, body, x_cart_token, register=True)


@router.post("/login", dependencies=[Depends(limited)])
def login(body: Credentials, x_cart_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    return authenticate(db, body, x_cart_token)


@router.get("/me")
def me(user=Depends(current_user)):
    return user_read(user)


@router.post("/logout", status_code=204)
def logout(authorization: str = Header(), db: Session = Depends(get_db)):
    session, _ = get_session(db, authorization)
    db.delete(session)
    db.commit()
