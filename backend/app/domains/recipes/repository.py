import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.ingredients.models import Ingredient
from app.domains.recipes.models import DishIngredient
from app.domains.suppliers.models import Supplier


class RecipeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def details(self, dish_id: uuid.UUID) -> list[DishIngredient]:
        return list(self.session.scalars(
            select(DishIngredient).where(DishIngredient.dish_id == dish_id)
            .order_by(DishIngredient.sort_order, DishIngredient.id)
        ))

    def ingredient_models(self, ingredient_ids: set[uuid.UUID]) -> dict[uuid.UUID, Ingredient]:
        if not ingredient_ids:
            return {}
        return {item.id: item for item in self.session.scalars(
            select(Ingredient).where(Ingredient.id.in_(ingredient_ids))
        )}

    def aggregate_rows(self, dish_id: uuid.UUID):
        return list(self.session.execute(
            select(
                DishIngredient.id, DishIngredient.dish_id, DishIngredient.ingredient_id,
                Ingredient.code.label("ingredient_code"), Ingredient.name.label("ingredient_name"),
                Ingredient.unit.label("ingredient_unit"), Ingredient.current_price,
                Supplier.name.label("supplier_name"), DishIngredient.quantity, DishIngredient.unit,
                DishIngredient.loss_rate, DishIngredient.sort_order, DishIngredient.notes,
                DishIngredient.created_at, DishIngredient.updated_at,
                DishIngredient.created_by, DishIngredient.updated_by,
            )
            .join(Ingredient, Ingredient.id == DishIngredient.ingredient_id)
            .outerjoin(Supplier, Supplier.id == Ingredient.primary_supplier_id)
            .where(DishIngredient.dish_id == dish_id)
            .order_by(DishIngredient.sort_order, DishIngredient.id)
        ).mappings())

    def add(self, detail: DishIngredient) -> None:
        self.session.add(detail)

    def delete(self, detail: DishIngredient) -> None:
        self.session.delete(detail)
