"""Acesso a dados de usuários, sessões de login e tentativas de autenticação."""
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.account import AccountSession, AuthAttempt
from app.models.user import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email))

    def add(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user

    def lock(self, user_id: int) -> None:
        """UPDATE sem mudar valores: trava a linha do usuário até o fim da transação."""
        self.db.execute(update(User).where(User.id == user_id).values(is_active=User.is_active))

    def set_admin(self, user_id: int, enabled: bool) -> None:
        self.db.execute(update(User).where(User.id == user_id).values(is_admin=enabled))


class SessionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, token_hash: str) -> AccountSession | None:
        return self.db.get(AccountSession, token_hash)

    def add(self, session: AccountSession) -> None:
        self.db.add(session)

    def delete(self, session: AccountSession) -> None:
        self.db.delete(session)

    def list_for_user(self, user_id: int, now) -> list[AccountSession]:
        return list(self.db.scalars(select(AccountSession).where(
            AccountSession.user_id == user_id, AccountSession.expires_at > now,
        ).order_by(AccountSession.created_at.desc().nullslast(), AccountSession.token_hash)))

    def get_public(self, user_id: int, public_id: str) -> AccountSession | None:
        return self.db.scalar(select(AccountSession).where(
            AccountSession.user_id == user_id, AccountSession.public_id == public_id))

    def touch(self, token_hash: str, now) -> None:
        self.db.execute(update(AccountSession).where(AccountSession.token_hash == token_hash)
                        .values(last_used_at=now))

    def trim(self, user_id: int, keep: int) -> int:
        """Mantém só as `keep` sessões mais novas da conta (as antigas são encerradas)."""
        old = list(self.db.scalars(select(AccountSession.token_hash).where(AccountSession.user_id == user_id)
                                   .order_by(AccountSession.created_at.desc().nullslast(),
                                             AccountSession.expires_at.desc()).offset(keep)))
        if old:
            self.db.execute(delete(AccountSession).where(AccountSession.token_hash.in_(old)))
        return len(old)

    def delete_expired(self, now) -> int:
        return self.db.execute(delete(AccountSession).where(AccountSession.expires_at < now)).rowcount

    def delete_all_for_user(self, user_id: int, keep_token_hash: str | None = None) -> None:
        statement = delete(AccountSession).where(AccountSession.user_id == user_id)
        if keep_token_hash:
            statement = statement.where(AccountSession.token_hash != keep_token_hash)
        self.db.execute(statement)


class AttemptRepository:
    def __init__(self, db: Session):
        self.db = db

    def delete_older_than(self, cutoff) -> int:
        return self.db.execute(delete(AuthAttempt).where(AuthAttempt.started_at < cutoff)).rowcount

    def get_locked(self, key: str) -> AuthAttempt:
        """Garante a linha do contador e a trava (contador compartilhado entre processos)."""
        if self.db.get(AuthAttempt, key) is None:
            try:
                with self.db.begin_nested():
                    self.db.add(AuthAttempt(key=key, count=0))
                    self.db.flush()
            except IntegrityError:
                pass
        self.db.execute(update(AuthAttempt).where(AuthAttempt.key == key).values(count=AuthAttempt.count))
        return self.db.get(AuthAttempt, key, populate_existing=True)
