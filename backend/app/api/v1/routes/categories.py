import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.domains.auth.dependencies import get_current_user, require_admin
from app.domains.auth.exceptions import InvalidCredentialsError
from app.domains.categories.exceptions import CategoryInUseError, CategoryNameExistsError, CategoryNotFoundError
from app.domains.categories.schemas import CategoryCreate, CategoryKind, CategoryList, CategoryPublic, CategoryUpdate
from app.domains.categories.service import CategoryService
from app.domains.users.models import User
from app.shared.schemas import PaginationMeta, PasswordConfirmation


router = APIRouter(prefix="/categories", tags=["categories"], dependencies=[Depends(get_current_user)])


def service(session: Session) -> CategoryService:
    return CategoryService(session)


def map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, CategoryNotFoundError):
        return HTTPException(404, "Category not found")
    if isinstance(exc, CategoryNameExistsError):
        return HTTPException(409, "Category name already exists")
    if isinstance(exc, CategoryInUseError):
        return HTTPException(409, "Category is referenced and cannot be permanently deleted")
    if isinstance(exc, InvalidCredentialsError):
        return HTTPException(401, "Password verification failed")
    return HTTPException(400, "Category operation failed")


@router.get("/{kind}", response_model=CategoryList)
def list_categories(kind: CategoryKind, session: Annotated[Session, Depends(get_db_session)], page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), active: bool | None = None) -> CategoryList:
    items, total = service(session).list(kind, page, page_size, active)
    return CategoryList(items=[CategoryPublic.model_validate(item) for item in items], pagination=PaginationMeta(page=page, page_size=page_size, total=total))


@router.get("/{kind}/{category_id}", response_model=CategoryPublic)
def get_category(kind: CategoryKind, category_id: uuid.UUID, session: Annotated[Session, Depends(get_db_session)]) -> CategoryPublic:
    try:
        return CategoryPublic.model_validate(service(session).get(kind, category_id))
    except Exception as exc:
        raise map_error(exc) from exc


@router.post("/{kind}", response_model=CategoryPublic, status_code=201)
def create_category(kind: CategoryKind, data: CategoryCreate, user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]) -> CategoryPublic:
    try:
        return CategoryPublic.model_validate(service(session).create(kind, data, user.id))
    except Exception as exc:
        raise map_error(exc) from exc


@router.patch("/{kind}/{category_id}", response_model=CategoryPublic)
def update_category(kind: CategoryKind, category_id: uuid.UUID, data: CategoryUpdate, user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]) -> CategoryPublic:
    try:
        return CategoryPublic.model_validate(service(session).update(kind, category_id, data, user.id))
    except Exception as exc:
        raise map_error(exc) from exc


@router.post("/{kind}/{category_id}/deactivate", response_model=CategoryPublic)
def deactivate_category(kind: CategoryKind, category_id: uuid.UUID, user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]) -> CategoryPublic:
    try:
        return CategoryPublic.model_validate(service(session).set_active(kind, category_id, False, user.id))
    except Exception as exc:
        raise map_error(exc) from exc


@router.post("/{kind}/{category_id}/reactivate", response_model=CategoryPublic)
def reactivate_category(kind: CategoryKind, category_id: uuid.UUID, user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]) -> CategoryPublic:
    try:
        return CategoryPublic.model_validate(service(session).set_active(kind, category_id, True, user.id))
    except Exception as exc:
        raise map_error(exc) from exc


@router.post("/{kind}/{category_id}/hard-delete", status_code=204)
def hard_delete_category(kind: CategoryKind, category_id: uuid.UUID, confirmation: PasswordConfirmation, user: Annotated[User, Depends(require_admin)], session: Annotated[Session, Depends(get_db_session)]) -> Response:
    try:
        service(session).hard_delete(kind, category_id, user.id, confirmation.password)
    except Exception as exc:
        raise map_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
