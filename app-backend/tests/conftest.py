import os
from collections.abc import Iterator

import pytest

os.environ["DATABASE_URL"] = "sqlite:///./test_sobracero.db"
os.environ["LLM_PROVIDER"] = "mock"


class InMemoryRefreshTokenStore:
    def __init__(self) -> None:
        self.sessions: dict[str, int] = {}

    def issue(self, token_id: str, user_id: int, ttl_seconds: int) -> bool:
        if token_id in self.sessions:
            return False
        self.sessions[token_id] = user_id
        return True

    def rotate(self, old_token_id: str, new_token_id: str, user_id: int, ttl_seconds: int) -> bool:
        if self.sessions.get(old_token_id) != user_id or new_token_id in self.sessions:
            return False
        del self.sessions[old_token_id]
        self.sessions[new_token_id] = user_id
        return True

    def revoke(self, token_id: str, user_id: int) -> None:
        if self.sessions.get(token_id) == user_id:
            del self.sessions[token_id]


@pytest.fixture(autouse=True)
def use_in_memory_auth_sessions() -> Iterator[None]:
    from app.config import settings
    from app.dependencies import get_session_manager
    from app.infrastructure.auth.refresh_sessions import JwtRedisSessionManager
    from app.main import app

    manager = JwtRedisSessionManager(
        settings.jwt_secret,
        InMemoryRefreshTokenStore(),
        settings.access_token_expire_minutes,
        settings.refresh_token_expire_days,
    )
    app.dependency_overrides[get_session_manager] = lambda: manager
    yield
    app.dependency_overrides.pop(get_session_manager, None)
