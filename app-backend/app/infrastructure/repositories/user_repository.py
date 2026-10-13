from typing import cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.dto import AuthUser, UserRole
from app.domain.exceptions import EmailAlreadyRegisteredError
from app.models import User


class SqlAlchemyAuthUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_email(self, email: str) -> AuthUser | None:
        user = self._session.scalar(select(User).where(User.email == email))
        return self._to_auth_user(user) if user else None

    def create_user(self, email: str, password_hash: str, role: UserRole) -> AuthUser:
        user = User(email=email, password_hash=password_hash, role=role)
        self._session.add(user)
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise EmailAlreadyRegisteredError("Email is already registered") from exc
        self._session.refresh(user)
        return self._to_auth_user(user)

    @staticmethod
    def _to_auth_user(user: User) -> AuthUser:
        if user.role not in {"business", "customer"}:
            raise ValueError(f"Unsupported authentication role in user record: {user.role}")
        return AuthUser(
            id=user.id,
            email=user.email,
            password_hash=user.password_hash,
            role=cast(UserRole, user.role),
            is_admin=user.is_admin,
        )
