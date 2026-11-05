"""Regras da área "Minha conta": perfil, troca de senha e endereços salvos."""
from sqlalchemy.orm import Session

from app.core.exceptions import NotFound, Unauthorized, Unprocessable
from app.core.security import hash_password, verify_password
from app.models.account import AccountSession
from app.models.address import Address
from app.models.user import User
from app.repositories.address_repository import AddressRepository
from app.repositories.user_repository import SessionRepository
from app.schemas.user import AddressSave, PasswordChange, ProfileWrite
from app.core.audit import security_event
from app.services import notification_service
from app.services.auth_service import throttle, user_read

MAX_ADDRESSES = 10


def address_read(address: Address) -> dict:
    return {"id": address.id, "label": address.label, "is_default": address.is_default, **address.snapshot()}


def update_profile(db: Session, user: User, body: ProfileWrite) -> dict:
    user.full_name = body.full_name or None
    user.phone = body.phone or None
    db.commit()
    return user_read(user)


def change_password(db: Session, user: User, session: AccountSession, body: PasswordChange) -> None:
    throttle(db, f"password:{user.id}", 10)
    if not verify_password(body.current_password, user.hashed_password):
        raise Unauthorized("Senha atual incorreta.")
    if body.new_password == body.current_password:
        raise Unprocessable("A nova senha precisa ser diferente da atual.")
    user.hashed_password = hash_password(body.new_password)
    # Troca de senha derruba as outras sessões (outro aparelho, alguém com a senha antiga).
    SessionRepository(db).delete_all_for_user(user.id, keep_token_hash=session.token_hash)
    notification_service.queue(db, "password_changed", user.email,
                               notification_service.base_context(name=user.full_name), user_id=user.id)
    db.commit()
    security_event("password.changed", user=user.id)


def list_addresses(db: Session, user: User) -> list[dict]:
    return [address_read(a) for a in AddressRepository(db).list_for_user(user.id)]


def _owned(db: Session, user: User, address_id: int) -> Address:
    address = AddressRepository(db).get_for_user(address_id, user.id)
    if address is None:
        raise NotFound("Endereço não encontrado.")
    return address


def add_address(db: Session, user: User, body: AddressSave) -> dict:
    addresses = AddressRepository(db)
    count = addresses.count_for_user(user.id)
    if count >= MAX_ADDRESSES:
        raise Unprocessable("Limite de 10 endereços por conta.")
    data = body.model_dump()
    # O primeiro endereço vira o padrão automaticamente.
    data["is_default"] = data["is_default"] or count == 0
    if data["is_default"]:
        addresses.clear_default(user.id)
    address = addresses.add(Address(user_id=user.id, **data))
    db.commit()
    return address_read(address)


def edit_address(db: Session, user: User, address_id: int, body: AddressSave) -> dict:
    address = _owned(db, user, address_id)
    data = body.model_dump()
    if data["is_default"] and not address.is_default:
        AddressRepository(db).clear_default(user.id)
    elif address.is_default:
        data["is_default"] = True  # para trocar o padrão, marque outro endereço
    for key, value in data.items():
        setattr(address, key, value)
    db.commit()
    return address_read(address)


def delete_address(db: Session, user: User, address_id: int) -> None:
    addresses = AddressRepository(db)
    address = _owned(db, user, address_id)
    was_default = address.is_default
    addresses.delete(address)
    db.flush()
    if was_default:
        remaining = addresses.list_for_user(user.id)
        if remaining:
            remaining[0].is_default = True
    db.commit()


def saved_address_snapshot(db: Session, user: User | None, address_id: int) -> dict:
    """Endereço salvo usado no checkout: só o da própria conta."""
    if user is None:
        raise Unauthorized("Entre na sua conta para usar um endereço salvo.")
    return _owned(db, user, address_id).snapshot()

