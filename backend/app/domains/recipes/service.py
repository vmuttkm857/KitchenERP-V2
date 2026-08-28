import uuid
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.dishes.service import DishService
from app.domains.recipes.exceptions import (
    DuplicateRecipeIngredientError, InvalidRecipeIngredientError, RecipeDetailIdentityError,
)
from app.domains.recipes.models import DishIngredient
from app.domains.recipes.repository import RecipeRepository
from app.domains.recipes.schemas import RecipeReplace
from app.shared.domain.quantities import calculate_recipe_cost, normalize_unit


class RecipeService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = RecipeRepository(session)
        self.dishes = DishService(session)

    def get(self, dish_id: uuid.UUID) -> dict:
        dish = self.dishes.get(dish_id)
        items: list[dict] = []
        total = Decimal("0")
        needs_review = False
        requirement_ready = True
        for row in self.repository.aggregate_rows(dish_id):
            item = dict(row)
            cost = calculate_recipe_cost(
                item["quantity"], item["loss_rate"], item["unit"],
                item["ingredient_unit"], item.pop("current_price"),
            )
            item["item_cost"] = cost
            item["cost_needs_review"] = cost is None
            needs_review = needs_review or cost is None
            requirement_ready = requirement_ready and item["quantity"] > 0
            if cost is not None:
                total += cost
            items.append(item)
        return {
            "dish": dish, "items": items,
            "total_cost": None if needs_review else total,
            "cost_needs_review": needs_review,
            "requirement_ready": bool(items) and requirement_ready,
        }

    def replace(self, dish_id: uuid.UUID, data: RecipeReplace, actor_id: uuid.UUID) -> dict:
        self.dishes.get_model(dish_id)
        ingredient_ids = [item.ingredient_id for item in data.items]
        if len(set(ingredient_ids)) != len(ingredient_ids):
            raise DuplicateRecipeIngredientError()
        ingredients = self.repository.ingredient_models(set(ingredient_ids))
        if len(ingredients) != len(set(ingredient_ids)) or any(not item.is_active for item in ingredients.values()):
            raise InvalidRecipeIngredientError("Every recipe ingredient must exist and be active")
        existing = {item.id: item for item in self.repository.details(dish_id)}
        retained: set[uuid.UUID] = set()
        for payload in data.items:
            if payload.unit.strip() == "mL":
                raise InvalidRecipeIngredientError("Use ml for new recipe data; legacy mL is not accepted at runtime")
            if payload.id is None:
                detail = DishIngredient(dish_id=dish_id, ingredient_id=payload.ingredient_id,
                                        created_by=actor_id, updated_by=actor_id)
                self.repository.add(detail)
            else:
                detail = existing.get(payload.id)
                if detail is None or detail.ingredient_id != payload.ingredient_id:
                    raise RecipeDetailIdentityError()
                retained.add(detail.id)
            detail.quantity = payload.quantity
            detail.unit = normalize_unit(payload.unit)
            detail.loss_rate = payload.loss_rate
            detail.sort_order = payload.sort_order
            detail.notes = payload.notes
            detail.updated_by = actor_id
        for detail_id, detail in existing.items():
            if detail_id not in retained:
                self.repository.delete(detail)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateRecipeIngredientError() from exc
        return self.get(dish_id)
