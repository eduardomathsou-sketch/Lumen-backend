"""Dá ou tira permissão de admin de uma conta existente; nunca é exposto como rota pública.

Uso: python -m app.admin_access grant --email voce@exemplo.com
"""
import argparse

from app.core.database import SessionLocal
import app.models.all  # noqa: F401  (registra todas as tabelas)
from app.repositories.user_repository import SessionRepository, UserRepository


def set_admin(db, email, enabled):
    target = UserRepository(db).get_by_email(email.strip().lower())
    if target is None or not target.is_active:
        raise ValueError('Cadastre primeiro uma conta ativa com esse e-mail na loja.')
    UserRepository(db).set_admin(target.id, enabled)
    # Sessões antigas não herdam a permissão nova: a pessoa precisa entrar de novo.
    SessionRepository(db).delete_all_for_user(target.id)
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
