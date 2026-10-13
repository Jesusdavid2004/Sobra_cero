from app.application.dto import SessionTokens, UserRole
from app.application.ports import AuthUserRepository, PasswordHasher, SessionManager
from app.domain.exceptions import EmailAlreadyRegisteredError, InvalidCredentialsError


class RegisterUser:
    def __init__(
        self,
        users: AuthUserRepository,
        password_hasher: PasswordHasher,
        sessions: SessionManager,
    ) -> None:
        self._users = users
        self._password_hasher = password_hasher
        self._sessions = sessions

    def execute(self, email: str, password: str, role: UserRole) -> SessionTokens:
        if self._users.find_by_email(email):
            raise EmailAlreadyRegisteredError("Email is already registered")
        password_hash = self._password_hasher.hash(password)
        user = self._users.create_user(email, password_hash, role)
        return self._sessions.issue(user.id)


class Login:
    def __init__(
        self,
        users: AuthUserRepository,
        password_hasher: PasswordHasher,
        sessions: SessionManager,
    ) -> None:
        self._users = users
        self._password_hasher = password_hasher
        self._sessions = sessions

    def execute(self, email: str, password: str) -> SessionTokens:
        user = self._users.find_by_email(email)
        if user is None or not self._password_hasher.verify(password, user.password_hash):
            raise InvalidCredentialsError("Invalid credentials")
        return self._sessions.issue(user.id)


class RefreshSession:
    def __init__(self, sessions: SessionManager) -> None:
        self._sessions = sessions

    def execute(self, refresh_token: str) -> SessionTokens:
        return self._sessions.rotate(refresh_token)


class LogoutSession:
    def __init__(self, sessions: SessionManager) -> None:
        self._sessions = sessions

    def execute(self, refresh_token: str | None) -> None:
        if refresh_token:
            self._sessions.revoke(refresh_token)
