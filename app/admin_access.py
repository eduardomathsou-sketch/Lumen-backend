"""Grant/revoke admin for an existing account; never exposed as a public API."""
import argparse
from sqlalchemy import delete, select, update
from app.core.database import SessionLocal
from app.models import account, cart, category, order, payment, product, user  # noqa: F401
from app.models.account import AccountSession
from app.models.user import User


def set_admin(db, email, enabled):
    target = db.scalar(select(User).where(User.email == email.strip().lower()))
    if target is None or not target.is_active:
        raise ValueError('Cadastre primeiro uma conta ativa com esse e-mail na loja.')
    db.execute(update(User).where(User.id == target.id).values(is_admin=enabled))
    # Existing sessions must not inherit newly granted privileges.
    db.execute(delete(AccountSession).where(AccountSession.user_id == target.id))
    db.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('grant', 'revoke'))
    parser.add_argument('--email', required=True)
    args = parser.parse_args()
    with SessionLocal() as db:
        try:
            set_admin(db, args.email, args.action == 'grant')
        except ValueError as exc:
            parser.error(str(exc))
    print('Permissão atualizada. Entre novamente na loja para iniciar uma nova sessão.')


if __name__ == '__main__':
    main()
