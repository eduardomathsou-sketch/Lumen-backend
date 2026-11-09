from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_session, current_user, get_db
from app.schemas.user import AddressSave, ConsentsWrite, PasswordChange, PasswordConfirm, ProfileWrite
from app.services import auth_service, privacy_service, user_service

router = APIRouter(prefix="/users/me", tags=["account"])


@router.get("")
def profile(user=Depends(current_user)):
    return auth_service.user_read(user)


@router.put("")
def update_profile(body: ProfileWrite, user=Depends(current_user), db: Session = Depends(get_db)):
    return user_service.update_profile(db, user, body)


@router.post("/password", status_code=204)
def change_password(body: PasswordChange, pair=Depends(current_session), db: Session = Depends(get_db)):
    session, user = pair
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


# --- Privacidade (LGPD) ---
@router.put("/consents")
def update_consents(body: ConsentsWrite, user=Depends(current_user), db: Session = Depends(get_db)):
    return privacy_service.update_consents(db, user, body)


@router.post("/data-export")
def export_data(body: PasswordConfirm, user=Depends(current_user), db: Session = Depends(get_db)):
    return privacy_service.export_data(db, user, body.password)


@router.post("/delete", status_code=204)
def delete_account(body: PasswordConfirm, user=Depends(current_user), db: Session = Depends(get_db)):
    privacy_service.delete_account(db, user, body.password)
