import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.domains.auth.dependencies import get_current_user, require_admin
from app.domains.auth.exceptions import InvalidCredentialsError
from app.domains.users.exceptions import LastActiveAdminError, UserNotFoundError, UsernameAlreadyExistsError
from app.domains.users.models import User
from app.domains.users.schemas import PasswordChange, PasswordReset, UserCreate, UserList, UserPublic, UserUpdate
from app.domains.users.service import UserService
from app.shared.schemas import PaginationMeta

router = APIRouter(prefix="/users", tags=["users"])


def mapped(exc: Exception) -> HTTPException:
    if isinstance(exc, UserNotFoundError): return HTTPException(404, "User not found")
    if isinstance(exc, UsernameAlreadyExistsError): return HTTPException(409, "Username already exists")
    if isinstance(exc, LastActiveAdminError): return HTTPException(409, "The last active administrator cannot be disabled or demoted")
    if isinstance(exc, InvalidCredentialsError): return HTTPException(401, "Password verification failed")
    return HTTPException(400, "User operation failed")


@router.get("", response_model=UserList)
def list_users(session: Annotated[Session, Depends(get_db_session)], admin: Annotated[User, Depends(require_admin)],
               page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
               search: str | None = None, active: bool | None = None,
               role: Literal["admin", "user"] | None = None):
    items, total = UserService(session).list(page, page_size, search, active, role)
    return UserList(items=[UserPublic.model_validate(item) for item in items],
                    pagination=PaginationMeta(page=page, page_size=page_size, total=total))


@router.post("", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, admin: Annotated[User, Depends(require_admin)],
                session: Annotated[Session, Depends(get_db_session)]):
    try: return UserPublic.model_validate(UserService(session).create_user(data, actor_id=admin.id))
    except Exception as exc: raise mapped(exc) from exc


@router.post("/me/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(data: PasswordChange, user: Annotated[User, Depends(get_current_user)],
                    session: Annotated[Session, Depends(get_db_session)]):
    try: UserService(session).change_password(user.id, data); return Response(status_code=204)
    except Exception as exc: raise mapped(exc) from exc


@router.get("/{user_id}", response_model=UserPublic)
def get_user(user_id: uuid.UUID, admin: Annotated[User, Depends(require_admin)],
             session: Annotated[Session, Depends(get_db_session)]):
    try: return UserPublic.model_validate(UserService(session).get(user_id))
    except Exception as exc: raise mapped(exc) from exc


@router.patch("/{user_id}", response_model=UserPublic)
def update_user(user_id: uuid.UUID, data: UserUpdate, admin: Annotated[User, Depends(require_admin)],
                session: Annotated[Session, Depends(get_db_session)]):
    try: return UserPublic.model_validate(UserService(session).update(user_id, data, admin.id))
    except Exception as exc: raise mapped(exc) from exc


@router.post("/{user_id}/deactivate", response_model=UserPublic)
def deactivate_user(user_id: uuid.UUID, admin: Annotated[User, Depends(require_admin)],
                    session: Annotated[Session, Depends(get_db_session)]):
    try: return UserPublic.model_validate(UserService(session).set_active(user_id, False, admin.id))
    except Exception as exc: raise mapped(exc) from exc


@router.post("/{user_id}/reactivate", response_model=UserPublic)
def reactivate_user(user_id: uuid.UUID, admin: Annotated[User, Depends(require_admin)],
                    session: Annotated[Session, Depends(get_db_session)]):
    try: return UserPublic.model_validate(UserService(session).set_active(user_id, True, admin.id))
    except Exception as exc: raise mapped(exc) from exc


@router.post("/{user_id}/reset-password", response_model=UserPublic)
def reset_password(user_id: uuid.UUID, data: PasswordReset, admin: Annotated[User, Depends(require_admin)],
                   session: Annotated[Session, Depends(get_db_session)]):
    try: return UserPublic.model_validate(UserService(session).reset_password(user_id, data, admin.id))
    except Exception as exc: raise mapped(exc) from exc
