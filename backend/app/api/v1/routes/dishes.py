import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.domains.auth.dependencies import get_current_user
from app.domains.auth.exceptions import InvalidCredentialsError
from app.domains.dishes.exceptions import (
    DishIdentityExistsError, DishInUseError, DishNotFoundError, InvalidDishCategoryError,
)
from app.domains.dishes.schemas import DishCreate, DishList, DishPublic, DishUpdate
from app.domains.dishes.service import DishService
from app.domains.users.models import User
from app.shared.schemas import PaginationMeta, PasswordConfirmation


router = APIRouter(prefix="/dishes", tags=["dishes"], dependencies=[Depends(get_current_user)])


def map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DishNotFoundError):
        return HTTPException(404, "Dish not found")
    if isinstance(exc, DishIdentityExistsError):
        return HTTPException(409, "Dish code or name already exists")
    if isinstance(exc, InvalidDishCategoryError):
        return HTTPException(422, "Dish category must exist and be active")
    if isinstance(exc, DishInUseError):
        return HTTPException(409, "Dish is referenced and cannot be permanently deleted")
    if isinstance(exc, InvalidCredentialsError):
        return HTTPException(401, "Password verification failed")
    return HTTPException(400, "Dish operation failed")


@router.get("", response_model=DishList)
def list_dishes(session: Annotated[Session, Depends(get_db_session)], page: int = Query(1, ge=1),
                page_size: int = Query(25, ge=1, le=100), active: bool | None = None,
                search: str | None = None, category_id: uuid.UUID | None = None) -> DishList:
    items, total = DishService(session).list(page, page_size, active, search, category_id)
    return DishList(items=[DishPublic.model_validate(item) for item in items],
                    pagination=PaginationMeta(page=page, page_size=page_size, total=total))


@router.get("/{dish_id}", response_model=DishPublic)
def get_dish(dish_id: uuid.UUID, session: Annotated[Session, Depends(get_db_session)]) -> DishPublic:
    try:
        return DishPublic.model_validate(DishService(session).get(dish_id))
    except Exception as exc:
        raise map_error(exc) from exc


@router.post("", response_model=DishPublic, status_code=201)
def create_dish(data: DishCreate, user: Annotated[User, Depends(get_current_user)],
                session: Annotated[Session, Depends(get_db_session)]) -> DishPublic:
    try:
        return DishPublic.model_validate(DishService(session).create(data, user.id))
    except Exception as exc:
        raise map_error(exc) from exc


@router.patch("/{dish_id}", response_model=DishPublic)
def update_dish(dish_id: uuid.UUID, data: DishUpdate, user: Annotated[User, Depends(get_current_user)],
                session: Annotated[Session, Depends(get_db_session)]) -> DishPublic:
    try:
        return DishPublic.model_validate(DishService(session).update(dish_id, data, user.id))
    except Exception as exc:
        raise map_error(exc) from exc


@router.post("/{dish_id}/deactivate", response_model=DishPublic)
def deactivate_dish(dish_id: uuid.UUID, user: Annotated[User, Depends(get_current_user)],
                    session: Annotated[Session, Depends(get_db_session)]) -> DishPublic:
    try:
        return DishPublic.model_validate(DishService(session).set_active(dish_id, False, user.id))
    except Exception as exc:
        raise map_error(exc) from exc


@router.post("/{dish_id}/reactivate", response_model=DishPublic)
def reactivate_dish(dish_id: uuid.UUID, user: Annotated[User, Depends(get_current_user)],
                    session: Annotated[Session, Depends(get_db_session)]) -> DishPublic:
    try:
        return DishPublic.model_validate(DishService(session).set_active(dish_id, True, user.id))
    except Exception as exc:
        raise map_error(exc) from exc


@router.post("/{dish_id}/hard-delete", status_code=204)
def hard_delete_dish(dish_id: uuid.UUID, confirmation: PasswordConfirmation,
                     user: Annotated[User, Depends(get_current_user)],
                     session: Annotated[Session, Depends(get_db_session)]) -> Response:
    try:
        DishService(session).hard_delete(dish_id, user.id, confirmation.password)
    except Exception as exc:
        raise map_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
