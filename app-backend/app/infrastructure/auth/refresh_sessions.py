from uuid import uuid4

import jwt
from redis import Redis
from redis.exceptions import RedisError

from app.application.dto import SessionTokens
from app.application.ports import RefreshTokenStore, SessionManager
from app.domain.exceptions import (
    InvalidRefreshTokenError,
    RefreshSessionStoreUnavailableError,
)

_ROTATE_SCRIPT = """
local owner = redis.call('GET', KEYS[1])
if owner ~= ARGV[1] then
  return 0
end
redis.call('DEL', KEYS[1])
redis.call('SET', KEYS[2], ARGV[1], 'EX', ARGV[2])
return 1
"""

_REVOKE_SCRIPT = """
local owner = redis.call('GET', KEYS[1])
if owner ~= ARGV[1] then
  return 0
end
return redis.call('DEL', KEYS[1])
"""


class RedisRefreshTokenStore:
    def __init__(self, client: Redis, key_prefix: str = "sobracero:auth:refresh:") -> None:
        self._client = client
        self._key_prefix = key_prefix

    def issue(self, token_id: str, user_id: int, ttl_seconds: int) -> bool:
        try:
            return bool(
                self._client.set(
                    self._key(token_id),
                    str(user_id),
                    ex=ttl_seconds,
                    nx=True,
                )
            )
        except RedisError as exc:
            raise RefreshSessionStoreUnavailableError("Refresh session store is unavailable") from exc

    def rotate(self, old_token_id: str, new_token_id: str, user_id: int, ttl_seconds: int) -> bool:
        try:
            result = self._client.eval(
                _ROTATE_SCRIPT,
                2,
                self._key(old_token_id),
                self._key(new_token_id),
                str(user_id),
                ttl_seconds,
            )
            return result == 1
        except RedisError as exc:
            raise RefreshSessionStoreUnavailableError("Refresh session store is unavailable") from exc

    def revoke(self, token_id: str, user_id: int) -> None:
        try:
            self._client.eval(_REVOKE_SCRIPT, 1, self._key(token_id), str(user_id))
        except RedisError as exc:
            raise RefreshSessionStoreUnavailableError("Refresh session store is unavailable") from exc

    def _key(self, token_id: str) -> str:
        return f"{self._key_prefix}{token_id}"


class JwtRedisSessionManager(SessionManager):
    def __init__(
        self,
        secret: str,
        token_store: RefreshTokenStore,
        access_token_minutes: int,
        refresh_token_days: int,
    ) -> None:
        self._secret = secret
        self._token_store = token_store
        self._access_token_minutes = access_token_minutes
        self._refresh_token_days = refresh_token_days

    def issue(self, user_id: int) -> SessionTokens:
        token_id = uuid4().hex
        ttl_seconds = self._refresh_token_days * 24 * 60 * 60
        refresh_token = self._encode_refresh_token(user_id, token_id, ttl_seconds)
        if not self._token_store.issue(token_id, user_id, ttl_seconds):
            raise RefreshSessionStoreUnavailableError("Could not create refresh session")
        return SessionTokens(
            access_token=self._encode_access_token(user_id),
            refresh_token=refresh_token,
        )

    def rotate(self, refresh_token: str) -> SessionTokens:
        user_id, old_token_id = self._decode_refresh_token(refresh_token)
        new_token_id = uuid4().hex
        ttl_seconds = self._refresh_token_days * 24 * 60 * 60
        new_refresh_token = self._encode_refresh_token(user_id, new_token_id, ttl_seconds)
        if not self._token_store.rotate(old_token_id, new_token_id, user_id, ttl_seconds):
            raise InvalidRefreshTokenError("Refresh token is invalid or has already been used")
        return SessionTokens(
            access_token=self._encode_access_token(user_id),
            refresh_token=new_refresh_token,
        )

    def revoke(self, refresh_token: str) -> None:
        try:
            user_id, token_id = self._decode_refresh_token(refresh_token)
        except InvalidRefreshTokenError:
            return
        self._token_store.revoke(token_id, user_id)

    def _encode_access_token(self, user_id: int) -> str:
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        return jwt.encode(
            {
                "sub": str(user_id),
                "iat": now,
                "exp": now + timedelta(minutes=self._access_token_minutes),
                "type": "access",
            },
            self._secret,
            algorithm="HS256",
        )

    def _encode_refresh_token(self, user_id: int, token_id: str, ttl_seconds: int) -> str:
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        return jwt.encode(
            {
                "sub": str(user_id),
                "iat": now,
                "exp": now + timedelta(seconds=ttl_seconds),
                "jti": token_id,
                "type": "refresh",
            },
            self._secret,
            algorithm="HS256",
        )

    def _decode_refresh_token(self, token: str) -> tuple[int, str]:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                options={"require": ["exp", "iat", "jti", "sub", "type"]},
            )
        except jwt.InvalidTokenError as exc:
            raise InvalidRefreshTokenError("Refresh token is invalid or expired") from exc
        token_id = payload.get("jti")
        subject = payload.get("sub")
        if payload.get("type") != "refresh" or not isinstance(token_id, str) or not isinstance(subject, str):
            raise InvalidRefreshTokenError("Refresh token is invalid")
        try:
            user_id = int(subject)
        except ValueError as exc:
            raise InvalidRefreshTokenError("Refresh token subject is invalid") from exc
        if user_id <= 0:
            raise InvalidRefreshTokenError("Refresh token subject is invalid")
        return user_id, token_id
