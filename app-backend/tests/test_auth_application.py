import pytest

from app.application.dto import AuthUser, SessionTokens
from app.application.use_cases.auth import (
    Login,
    LogoutSession,
    RefreshSession,
    RegisterUser,
)
from app.domain.exceptions import EmailAlreadyRegisteredError, InvalidCredentialsError


class InMemoryUsers:
    def __init__(self) -> None:
        self.users: dict[str, AuthUser] = {}
        self.next_id = 1

    def find_by_email(self, email: str) -> AuthUser | None:
        return self.users.get(email)

    def create_user(self, email: str, password_hash: str, role: str) -> AuthUser:
        user = AuthUser(self.next_id, email, password_hash, role, False)
        self.users[email] = user
        self.next_id += 1
        return user


class PrefixPasswordHasher:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return self.hash(password) == password_hash


class RecordingSessions:
    def __init__(self) -> None:
        self.issued_for: list[int] = []
        self.rotated: list[str] = []
        self.revoked: list[str] = []

    def issue(self, user_id: int) -> SessionTokens:
        self.issued_for.append(user_id)
        return SessionTokens("access", "refresh")

    def rotate(self, refresh_token: str) -> SessionTokens:
        self.rotated.append(refresh_token)
        return SessionTokens("new-access", "new-refresh")

    def revoke(self, refresh_token: str) -> None:
        self.revoked.append(refresh_token)


def test_register_user_hashes_password_and_issues_a_session() -> None:
    users = InMemoryUsers()
    sessions = RecordingSessions()
    use_case = RegisterUser(users, PrefixPasswordHasher(), sessions)

    result = use_case.execute("person@example.com", "safe-password", "business")

    assert users.users["person@example.com"].password_hash == "hashed:safe-password"
    assert sessions.issued_for == [1]
    assert result == SessionTokens("access", "refresh")


def test_register_user_rejects_an_existing_email() -> None:
    users = InMemoryUsers()
    users.create_user("person@example.com", "hashed:old", "customer")

    with pytest.raises(EmailAlreadyRegisteredError):
        RegisterUser(users, PrefixPasswordHasher(), RecordingSessions()).execute(
            "person@example.com", "safe-password", "business"
        )


def test_login_rejects_missing_users_and_invalid_passwords() -> None:
    users = InMemoryUsers()
    sessions = RecordingSessions()
    login = Login(users, PrefixPasswordHasher(), sessions)
    users.create_user("person@example.com", "hashed:safe-password", "customer")

    with pytest.raises(InvalidCredentialsError):
        login.execute("missing@example.com", "safe-password")
    with pytest.raises(InvalidCredentialsError):
        login.execute("person@example.com", "wrong-password")
    assert sessions.issued_for == []


def test_login_issues_a_session_for_valid_credentials() -> None:
    users = InMemoryUsers()
    users.create_user("person@example.com", "hashed:safe-password", "customer")
    sessions = RecordingSessions()

    result = Login(users, PrefixPasswordHasher(), sessions).execute("person@example.com", "safe-password")

    assert sessions.issued_for == [1]
    assert result.access_token == "access"


def test_refresh_and_logout_use_session_manager() -> None:
    sessions = RecordingSessions()

    refreshed = RefreshSession(sessions).execute("old-refresh")
    LogoutSession(sessions).execute("new-refresh")
    LogoutSession(sessions).execute(None)

    assert refreshed == SessionTokens("new-access", "new-refresh")
    assert sessions.rotated == ["old-refresh"]
    assert sessions.revoked == ["new-refresh"]
