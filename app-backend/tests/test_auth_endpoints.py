import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import User


def test_registration_sets_http_only_refresh_cookie_and_returns_only_access_token() -> None:
    response = TestClient(app).post(
        "/api/v1/auth/register",
        json={"email": "auth-cookie@example.com", "password": "password123", "role": "customer"},
    )

    assert response.status_code == 201
    assert set(response.json()) == {"access_token", "token_type"}
    cookie = response.headers["set-cookie"]
    assert "sc_refresh=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/api/v1/auth" in cookie
    assert "refresh_token" not in response.json()

    claims = jwt.decode(response.json()["access_token"], settings.jwt_secret, algorithms=["HS256"])
    assert claims["type"] == "access"
    assert claims["exp"] - claims["iat"] <= settings.access_token_expire_minutes * 60


def test_login_accepts_existing_bcrypt_hash_and_issues_refresh_cookie() -> None:
    email = "legacy-hash@example.com"
    existing_hash = "$2b$12$lHOkLOCLdBo7QbTorO5O1.z/O4atQclJ8LTDZkUojw3q6ricz8yVC"
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            db.add(User(email=email, password_hash=existing_hash, role="customer"))
        else:
            user.password_hash = existing_hash
        db.commit()

    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )

    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]


def test_refresh_rotates_cookie_and_rejects_replayed_token() -> None:
    client = TestClient(app)
    registration = client.post(
        "/api/v1/auth/register",
        json={"email": "rotate@example.com", "password": "password123"},
    )
    old_refresh_token = registration.cookies["sc_refresh"]
    client.cookies.set("sc_refresh", old_refresh_token, path="/api/v1/auth")

    refreshed = client.post("/api/v1/auth/refresh")

    assert refreshed.status_code == 200
    assert refreshed.cookies["sc_refresh"] != old_refresh_token
    assert set(refreshed.json()) == {"access_token", "token_type"}
    client.cookies.set("sc_refresh", old_refresh_token, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_refresh_requires_a_cookie() -> None:
    response = TestClient(app).post("/api/v1/auth/refresh")

    assert response.status_code == 401


def test_logout_revokes_refresh_session_and_clears_cookie() -> None:
    client = TestClient(app)
    registration = client.post(
        "/api/v1/auth/register",
        json={"email": "logout@example.com", "password": "password123"},
    )
    refresh_token = registration.cookies["sc_refresh"]

    logout = client.post("/api/v1/auth/logout")

    assert logout.status_code == 204
    assert "Max-Age=0" in logout.headers["set-cookie"]
    assert "HttpOnly" in logout.headers["set-cookie"]
    client.cookies.set("sc_refresh", refresh_token, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_refresh_token_cannot_authenticate_as_an_access_token() -> None:
    client = TestClient(app)
    registration = client.post(
        "/api/v1/auth/register",
        json={"email": "token-type@example.com", "password": "password123"},
    )
    refresh_token = registration.cookies["sc_refresh"]

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh_token}"})

    assert response.status_code == 401


def test_registration_rejects_passwords_longer_than_bcrypt_input_limit() -> None:
    response = TestClient(app).post(
        "/api/v1/auth/register",
        json={"email": "long-password@example.com", "password": "é" * 37},
    )

    assert response.status_code == 422
