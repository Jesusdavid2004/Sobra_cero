from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from app.application.use_cases.auth import (
    Login,
    LogoutSession,
    RefreshSession,
    RegisterUser,
)
from app.auth import current_user
from app.config import settings
from app.dependencies import (
    get_login_use_case,
    get_logout_session_use_case,
    get_refresh_session_use_case,
    get_register_user_use_case,
)
from app.domain.exceptions import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)
from app.models import User
from app.schemas import LoginRequest, Token, UserCreate, UserOut

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path=settings.refresh_cookie_path,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite=settings.refresh_cookie_samesite,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite=settings.refresh_cookie_samesite,
    )


def token_response(response: Response, access_token: str, refresh_token: str) -> Token:
    set_refresh_cookie(response, refresh_token)
    return Token(access_token=access_token)


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(
    data: UserCreate,
    response: Response,
    use_case: RegisterUser = Depends(get_register_user_use_case),
) -> Token:
    try:
        tokens = use_case.execute(str(data.email), data.password, data.role)
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered") from exc
    return token_response(response, tokens.access_token, tokens.refresh_token)


@router.post("/login", response_model=Token)
def login(
    data: LoginRequest,
    response: Response,
    use_case: Login = Depends(get_login_use_case),
) -> Token:
    try:
        tokens = use_case.execute(str(data.email), data.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials") from exc
    return token_response(response, tokens.access_token, tokens.refresh_token)


@router.post("/refresh", response_model=Token)
def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=settings.refresh_cookie_name),
    use_case: RefreshSession = Depends(get_refresh_session_use_case),
) -> Token:
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    try:
        tokens = use_case.execute(refresh_token)
    except InvalidRefreshTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials") from exc
    return token_response(response, tokens.access_token, tokens.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=settings.refresh_cookie_name),
    use_case: LogoutSession = Depends(get_logout_session_use_case),
) -> Response:
    use_case.execute(refresh_token)
    clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user
