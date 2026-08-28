import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domains.categories.models import DishCategory
from app.domains.dishes.models import Dish


class DishRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, dish: Dish) -> None:
        self.session.add(dish)

    def get_model(self, dish_id: uuid.UUID) -> Dish | None:
        return self.session.get(Dish, dish_id)

    def category(self, category_id: uuid.UUID) -> DishCategory | None:
        return self.session.get(DishCategory, category_id)

    def identity_exists(self, code: str, name: str, exclude_id: uuid.UUID | None = None) -> bool:
        statement = select(Dish.id).where(
            or_(func.lower(Dish.code) == code.lower(), func.lower(Dish.name) == name.lower())
        )
        if exclude_id:
            statement = statement.where(Dish.id != exclude_id)
        return self.session.scalar(statement.limit(1)) is not None

    def _view_statement(self):
        return (
            select(
                Dish.id, Dish.code, Dish.name, Dish.category_id,
                DishCategory.name.label("category_name"), Dish.notes, Dish.is_active,
                Dish.created_at, Dish.updated_at, Dish.created_by, Dish.updated_by,
            )
            .outerjoin(DishCategory, DishCategory.id == Dish.category_id)
        )

    def get_view(self, dish_id: uuid.UUID):
        return self.session.execute(self._view_statement().where(Dish.id == dish_id)).mappings().one_or_none()

    def list(
        self, page: int, page_size: int, active: bool | None, search: str | None,
        category_id: uuid.UUID | None,
    ) -> tuple[list[dict], int]:
        filters = []
        if active is not None:
            filters.append(Dish.is_active == active)
        if category_id:
            filters.append(Dish.category_id == category_id)
        if search:
            term = f"%{search.strip().lower()}%"
            filters.append(or_(func.lower(Dish.code).like(term), func.lower(Dish.name).like(term)))
        total = self.session.scalar(select(func.count()).select_from(Dish).where(*filters)) or 0
        statement = (
            self._view_statement().where(*filters)
            .order_by(func.lower(Dish.code), Dish.id)
            .offset((page - 1) * page_size).limit(page_size)
        )
        return [dict(row) for row in self.session.execute(statement).mappings()], total

    def has_recipe(self, dish_id: uuid.UUID) -> bool:
        from app.domains.recipes.models import DishIngredient
        return self.session.scalar(
            select(DishIngredient.id).where(DishIngredient.dish_id == dish_id).limit(1)
        ) is not None

    def delete(self, dish: Dish) -> None:
        self.session.delete(dish)
