import hashlib
import secrets
from datetime import timedelta
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.core.security import hash_password, verify_password
from app.models.account import AccountSession, AccountCart, AuthAttempt
from app.models.cart import Cart
from app.models.user import User
from app.models.payment import utc_now, as_utc


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def user_read(user):
    return {"id": user.id, "email": user.email, "is_admin": user.is_admin}


def get_session(db, authorization):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Entre na sua conta para continuar.")
    session = db.get(AccountSession, digest(authorization[7:]))
    if not session or as_utc(session.expires_at) <= utc_now():
        raise HTTPException(401, "Sua sessão expirou. Entre novamente.")
    user = db.get(User, session.user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "Sessão indisponível. Entre novamente.")
    return session, user


def optional_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    return get_session(db, authorization)[1] if authorization else None


def current_user(user=Depends(optional_user)):
    if user is None:
        raise HTTPException(401, "Entre na sua conta para continuar.")
    return user


def current_admin(user=Depends(current_user)):
    if not user.is_admin:
        raise HTTPException(403, "Acesso restrito à administração da loja.")
    return user


def throttle(db, identity, limit):
    # Database-backed counter shared by workers; never trust forwarded IP headers here.
    key = digest(identity)
    row = db.get(AuthAttempt, key)
    if row is None:
        try:
            with db.begin_nested():
                db.add(AuthAttempt(key=key, count=0))
                db.flush()
        except IntegrityError:
            pass
    db.execute(update(AuthAttempt).where(AuthAttempt.key == key).values(count=AuthAttempt.count))
    row = db.get(AuthAttempt, key, populate_existing=True)
    if as_utc(row.started_at) < utc_now() - timedelta(minutes=15):
        row.count = 0
        row.started_at = utc_now()
    if row.count >= limit:
        db.commit()
        raise HTTPException(429, "Muitas tentativas. Aguarde 15 minutos e tente novamente.", headers={"Retry-After": "900"})
    row.count += 1
    db.commit()


def authenticate(db: Session, body, cart_token, *, register=False):
    user = db.scalar(select(User).where(User.email == body.email))
    if register:
        password_hash = hash_password(body.password)
        if user:
            raise HTTPException(409, "Não foi possível cadastrar. Confira os dados ou entre na sua conta.")
        user = User(email=body.email, hashed_password=password_hash)
        db.add(user)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "Não foi possível cadastrar. Confira os dados ou entre na sua conta.") from exc
    else:
        # Equal-cost hash for an unknown account avoids a fast existence probe.
        if user:
            valid = verify_password(body.password, user.hashed_password)
        else:
            hash_password(body.password)
            valid = False
        if not user or not valid or not user.is_active:
            raise HTTPException(401, "E-mail ou senha incorretos.")
    db.execute(update(User).where(User.id == user.id).values(is_active=User.is_active))
    link = db.get(AccountCart, user.id)
    if link is None:
        cart = db.scalar(select(Cart).where(Cart.token_hash == digest(cart_token or "")))
        if cart:
            from app.services.commerce_service import lock_cart
            lock_cart(db, cart)
            if db.scalar(select(AccountCart).where(AccountCart.cart_id == cart.id)):
                cart = None
        if cart is None:
            cart = Cart(token_hash=digest(secrets.token_urlsafe(32)), items=[])
            db.add(cart)
            db.flush()
        db.add(AccountCart(user_id=user.id, cart_id=cart.id))
    token = secrets.token_urlsafe(48)
    db.add(AccountSession(token_hash=digest(token), user_id=user.id, expires_at=utc_now() + timedelta(days=7)))
    db.commit()
    return {"access_token": token, "token_type": "bearer", "user": user_read(user)}
