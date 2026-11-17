from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.infrastructure.auth.password_hasher import BcryptPasswordHasher
from app.models import User

password_hasher = BcryptPasswordHasher()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def create_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {"sub": str(user_id), "iat": datetime.now(timezone.utc), "exp": expires, "type": "access"},
        settings.jwt_secret,
        algorithm="HS256",
    )


def current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_error = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
        )
        subject = payload.get("sub")
        if payload.get("type", "access") != "access" or not isinstance(subject, str):
            raise ValueError("Invalid access token")
        user_id = int(subject)
    except (jwt.InvalidTokenError, TypeError, ValueError):
        raise credentials_error
    user = db.get(User, user_id)
    if not user:
        raise credentials_error
    return user
