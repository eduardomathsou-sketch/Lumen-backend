from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db
from app.schemas.user import AddressSave, PasswordChange, ProfileWrite
from app.services import auth_service, user_service

router = APIRouter(prefix="/users/me", tags=["account"])


@router.get("")
def profile(user=Depends(current_user)):
    return auth_service.user_read(user)


@router.put("")
def update_profile(body: ProfileWrite, user=Depends(current_user), db: Session = Depends(get_db)):
    return user_service.update_profile(db, user, body)


@router.post("/password", status_code=204)
def change_password(body: PasswordChange, authorization: str = Header(), db: Session = Depends(get_db)):
    session, user = auth_service.get_session(db, authorization)
    user_service.change_password(db, user, session, body)


@router.get("/addresses")
def addresses(user=Depends(current_user), db: Session = Depends(get_db)):
    return user_service.list_addresses(db, user)


@router.post("/addresses", status_code=201)
def add_address(body: AddressSave, user=Depends(current_user), db: Session = Depends(get_db)):
    return user_service.add_address(db, user, body)


@router.put("/addresses/{address_id}")
def edit_address(address_id: int, body: AddressSave, user=Depends(current_user), db: Session = Depends(get_db)):
    return user_service.edit_address(db, user, address_id, body)


@router.delete("/addresses/{address_id}", status_code=204)
def delete_address(address_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
    user_service.delete_address(db, user, address_id)
