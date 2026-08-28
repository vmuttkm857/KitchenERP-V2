import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.categories.models import DishCategory, IngredientCategory, MenuCategory
from app.domains.categories.schemas import CategoryKind


CATEGORY_MODELS = {
    "ingredient": IngredientCategory,
    "dish": DishCategory,
    "menu": MenuCategory,
}


class CategoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def model_for(self, kind: CategoryKind) -> type[Any]:
        return CATEGORY_MODELS[kind]

    def add(self, category: Any) -> None:
        self.session.add(category)

    def get(self, kind: CategoryKind, category_id: uuid.UUID) -> Any | None:
        return self.session.get(self.model_for(kind), category_id)

    def name_exists(self, kind: CategoryKind, name: str, exclude_id: uuid.UUID | None = None) -> bool:
        model = self.model_for(kind)
        statement = select(model.id).where(func.lower(model.name) == name.lower())
        if exclude_id:
            statement = statement.where(model.id != exclude_id)
        return self.session.scalar(statement.limit(1)) is not None

    def list(self, kind: CategoryKind, page: int, page_size: int, active: bool | None) -> tuple[list[Any], int]:
        model = self.model_for(kind)
        filters = [] if active is None else [model.is_active == active]
        total = self.session.scalar(select(func.count()).select_from(model).where(*filters)) or 0
        statement = (
            select(model)
            .where(*filters)
            .order_by(model.sort_order, func.lower(model.name), model.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.session.scalars(statement)), total

    def has_references(self, kind: CategoryKind, category_id: uuid.UUID) -> bool:
        if kind != "ingredient":
            return False
        from app.domains.ingredients.models import Ingredient

        return self.session.scalar(
            select(Ingredient.id).where(Ingredient.category_id == category_id).limit(1)
        ) is not None

    def delete(self, category: Any) -> None:
        self.session.delete(category)
