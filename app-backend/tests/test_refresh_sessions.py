import jwt
import pytest
from redis.exceptions import RedisError

from app.domain.exceptions import (
    InvalidRefreshTokenError,
    RefreshSessionStoreUnavailableError,
)
from app.infrastructure.auth.refresh_sessions import (
    JwtRedisSessionManager,
    RedisRefreshTokenStore,
)


class InMemoryRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def eval(self, script: str, number_of_keys: int, *arguments: object) -> int:
        keys = [str(value) for value in arguments[:number_of_keys]]
        values = [str(value) for value in arguments[number_of_keys:]]
        if len(keys) == 2:
            old_key, new_key = keys
            user_id, _ttl = values
            if self.values.get(old_key) != user_id or new_key in self.values:
                return 0
            del self.values[old_key]
            self.values[new_key] = user_id
            return 1
        key = keys[0]
        user_id = values[0]
        if self.values.get(key) != user_id:
            return 0
        del self.values[key]
        return 1


class UnavailableRedis:
    def set(self, *args: object, **kwargs: object) -> None:
        raise RedisError("redis unavailable")

    def eval(self, *args: object, **kwargs: object) -> None:
        raise RedisError("redis unavailable")


def session_manager(redis: InMemoryRedis) -> JwtRedisSessionManager:
    return JwtRedisSessionManager(
        secret="test-secret-with-at-least-thirty-two-characters",
        token_store=RedisRefreshTokenStore(redis),  # type: ignore[arg-type]
        access_token_minutes=15,
        refresh_token_days=30,
    )


def test_refresh_token_rotates_once_and_can_be_revoked() -> None:
    manager = session_manager(InMemoryRedis())
    issued = manager.issue(7)
    access_claims = jwt.decode(
        issued.access_token,
        "test-secret-with-at-least-thirty-two-characters",
        algorithms=["HS256"],
    )
    refresh_claims = jwt.decode(
        issued.refresh_token,
        "test-secret-with-at-least-thirty-two-characters",
        algorithms=["HS256"],
    )

    assert access_claims["type"] == "access"
    assert refresh_claims["type"] == "refresh"
    rotated = manager.rotate(issued.refresh_token)
    assert rotated.refresh_token != issued.refresh_token

    with pytest.raises(InvalidRefreshTokenError):
        manager.rotate(issued.refresh_token)

    manager.revoke(rotated.refresh_token)
    with pytest.raises(InvalidRefreshTokenError):
        manager.rotate(rotated.refresh_token)


def test_refresh_store_reports_redis_failures() -> None:
    store = RedisRefreshTokenStore(UnavailableRedis())  # type: ignore[arg-type]

    with pytest.raises(RefreshSessionStoreUnavailableError):
        store.issue("token-id", 1, 60)
    with pytest.raises(RefreshSessionStoreUnavailableError):
        store.rotate("old-token-id", "new-token-id", 1, 60)
    with pytest.raises(RefreshSessionStoreUnavailableError):
        store.revoke("token-id", 1)
