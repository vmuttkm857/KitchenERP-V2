from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from app.core.config import settings
from app.domains.auth.dependencies import get_auth_service, get_current_user
from app.domains.auth.exceptions import AuthenticationError
from app.domains.auth.schemas import AuthResponse, LoginRequest, MessageResponse
from app.domains.auth.service import AuthResult, AuthService
from app.domains.users.models import User
from app.domains.users.schemas import UserPublic


router = APIRouter(prefix="/auth", tags=["authentication"])


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        path="/api/v1/auth",
    )


def _auth_response(result: AuthResult) -> AuthResponse:
    return AuthResponse(
        access_token=result.access_token,
        expires_in=settings.access_token_minutes * 60,
        user=UserPublic.model_validate(result.user),
    )


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication failed",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthResponse:
    try:
        result = service.login(payload.username, payload.password)
    except AuthenticationError as exc:
        raise _unauthorized() from exc
    _set_refresh_cookie(response, result.refresh_token)
    return _auth_response(result)


@router.post("/refresh", response_model=AuthResponse)
def refresh(
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    refresh_token: Annotated[str | None, Cookie(alias=settings.refresh_cookie_name)] = None,
) -> AuthResponse:
    if not refresh_token:
        raise _unauthorized()
    try:
        result = service.refresh(refresh_token)
    except AuthenticationError as exc:
        raise _unauthorized() from exc
    _set_refresh_cookie(response, result.refresh_token)
    return _auth_response(result)


@router.post("/logout", response_model=MessageResponse)
def logout(
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    refresh_token: Annotated[str | None, Cookie(alias=settings.refresh_cookie_name)] = None,
) -> MessageResponse:
    service.logout(refresh_token)
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path="/api/v1/auth",
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
    )
    return MessageResponse(message="Logged out")


@router.get("/me", response_model=UserPublic)
def me(user: Annotated[User, Depends(get_current_user)]) -> UserPublic:
    return UserPublic.model_validate(user)
