import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_auth_configuration_requires_a_strong_secret_and_secure_cookie() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(
            app_environment="production",
            jwt_secret="short-secret",
            refresh_cookie_secure=True,
        )

    with pytest.raises(ValidationError, match="refresh cookies must be secure"):
        Settings(
            app_environment="production",
            jwt_secret="production-secret-that-is-at-least-32-characters",
        )

    Settings(
        app_environment="production",
        jwt_secret="production-secret-that-is-at-least-32-characters",
        refresh_cookie_secure=True,
    )


def test_samesite_none_requires_secure_cookie() -> None:
    with pytest.raises(ValidationError, match="SameSite=None"):
        Settings(refresh_cookie_samesite="none")
