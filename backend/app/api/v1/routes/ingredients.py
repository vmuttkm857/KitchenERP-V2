import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.domains.auth.dependencies import get_current_user
from app.domains.auth.exceptions import InvalidCredentialsError
from app.domains.ingredients.exceptions import IngredientCodeExistsError, IngredientInUseError, IngredientNotFoundError, InvalidIngredientReferenceError
from app.domains.ingredients.schemas import IngredientCreate, IngredientList, IngredientPublic, IngredientUpdate, PriceHistoryPublic
from app.domains.ingredients.service import IngredientService
from app.domains.users.models import User
from app.shared.schemas import PaginationMeta, PasswordConfirmation


router = APIRouter(prefix="/ingredients", tags=["ingredients"], dependencies=[Depends(get_current_user)])


def map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, IngredientNotFoundError): return HTTPException(404, "Ingredient not found")
    if isinstance(exc, IngredientCodeExistsError): return HTTPException(409, "Ingredient code already exists")
    if isinstance(exc, InvalidIngredientReferenceError): return HTTPException(422, str(exc))
    if isinstance(exc, IngredientInUseError): return HTTPException(409, "Ingredient has price or business history and cannot be permanently deleted")
    if isinstance(exc, InvalidCredentialsError): return HTTPException(401, "Password verification failed")
    return HTTPException(400, "Ingredient operation failed")


@router.get("", response_model=IngredientList)
def list_ingredients(session: Annotated[Session, Depends(get_db_session)], page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), active: bool | None = None, search: str | None = None, category_id: uuid.UUID | None = None) -> IngredientList:
    items, total = IngredientService(session).list(page, page_size, active, search, category_id)
    return IngredientList(items=[IngredientPublic.model_validate(item) for item in items], pagination=PaginationMeta(page=page, page_size=page_size, total=total))


@router.get("/{ingredient_id}", response_model=IngredientPublic)
def get_ingredient(ingredient_id: uuid.UUID, session: Annotated[Session, Depends(get_db_session)]) -> IngredientPublic:
    try: return IngredientPublic.model_validate(IngredientService(session).get(ingredient_id))
    except Exception as exc: raise map_error(exc) from exc


@router.get("/{ingredient_id}/price-history", response_model=list[PriceHistoryPublic])
def price_history(ingredient_id: uuid.UUID, session: Annotated[Session, Depends(get_db_session)]) -> list[PriceHistoryPublic]:
    try: return [PriceHistoryPublic.model_validate(item) for item in IngredientService(session).price_history(ingredient_id)]
    except Exception as exc: raise map_error(exc) from exc


@router.post("", response_model=IngredientPublic, status_code=201)
def create_ingredient(data: IngredientCreate, user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]) -> IngredientPublic:
    try: return IngredientPublic.model_validate(IngredientService(session).create(data, user.id))
    except Exception as exc: raise map_error(exc) from exc


@router.patch("/{ingredient_id}", response_model=IngredientPublic)
def update_ingredient(ingredient_id: uuid.UUID, data: IngredientUpdate, user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]) -> IngredientPublic:
    try: return IngredientPublic.model_validate(IngredientService(session).update(ingredient_id, data, user.id))
    except Exception as exc: raise map_error(exc) from exc


@router.post("/{ingredient_id}/deactivate", response_model=IngredientPublic)
def deactivate_ingredient(ingredient_id: uuid.UUID, user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]) -> IngredientPublic:
    try: return IngredientPublic.model_validate(IngredientService(session).set_active(ingredient_id, False, user.id))
    except Exception as exc: raise map_error(exc) from exc


@router.post("/{ingredient_id}/reactivate", response_model=IngredientPublic)
def reactivate_ingredient(ingredient_id: uuid.UUID, user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]) -> IngredientPublic:
    try: return IngredientPublic.model_validate(IngredientService(session).set_active(ingredient_id, True, user.id))
    except Exception as exc: raise map_error(exc) from exc


@router.post("/{ingredient_id}/hard-delete", status_code=204)
def hard_delete_ingredient(ingredient_id: uuid.UUID, confirmation: PasswordConfirmation, user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]):
    try: IngredientService(session).hard_delete(ingredient_id, user.id, confirmation.password)
    except Exception as exc: raise map_error(exc) from exc
    return None
