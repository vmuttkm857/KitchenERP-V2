from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.domains.auth.exceptions import InvalidAccessTokenError
from app.domains.auth.service import AuthService
from app.domains.users.models import User


bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service(session: Annotated[Session, Depends(get_db_session)]) -> AuthService:
    return AuthService(session)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise InvalidAccessTokenError("Invalid access token")
    return service.get_current_user(credentials.credentials)
