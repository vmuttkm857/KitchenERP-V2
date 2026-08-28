import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.domains.auth.dependencies import get_current_user
from app.domains.dishes.exceptions import DishNotFoundError
from app.domains.recipes.exceptions import (
    DuplicateRecipeIngredientError, InvalidRecipeIngredientError, RecipeDetailIdentityError,
)
from app.domains.recipes.schemas import RecipeAggregate, RecipeReplace
from app.domains.recipes.service import RecipeService
from app.domains.users.models import User


router = APIRouter(prefix="/dishes/{dish_id}/recipe", tags=["recipes"], dependencies=[Depends(get_current_user)])


def map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DishNotFoundError):
        return HTTPException(404, "Dish not found")
    if isinstance(exc, DuplicateRecipeIngredientError):
        return HTTPException(409, "An ingredient may appear only once in a dish recipe")
    if isinstance(exc, InvalidRecipeIngredientError):
        return HTTPException(422, str(exc))
    if isinstance(exc, RecipeDetailIdentityError):
        return HTTPException(422, "Recipe detail does not belong to this dish or ingredient")
    return HTTPException(400, "Recipe operation failed")


@router.get("", response_model=RecipeAggregate)
def get_recipe(dish_id: uuid.UUID, session: Annotated[Session, Depends(get_db_session)]) -> RecipeAggregate:
    try:
        return RecipeAggregate.model_validate(RecipeService(session).get(dish_id))
    except Exception as exc:
        raise map_error(exc) from exc


@router.put("", response_model=RecipeAggregate)
def replace_recipe(dish_id: uuid.UUID, data: RecipeReplace,
                   user: Annotated[User, Depends(get_current_user)],
                   session: Annotated[Session, Depends(get_db_session)]) -> RecipeAggregate:
    try:
        return RecipeAggregate.model_validate(RecipeService(session).replace(dish_id, data, user.id))
    except Exception as exc:
        raise map_error(exc) from exc
