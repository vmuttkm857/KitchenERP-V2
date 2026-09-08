import uuid

from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.orm import Session

from app.domains.dishes.models import Dish
from app.domains.ingredients.models import Ingredient
from app.domains.postpartum.models import (
    PostpartumCase, PostpartumRestrictionGroup, PostpartumRestrictionGroupDish,
    PostpartumRestrictionGroupIngredient, PostpartumRoomHistory, PostpartumServicePause,
)
from app.shared.sorting import natural_code_order


class PostpartumRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, value): self.session.add(value)
    def delete(self, value): self.session.delete(value)
    def case(self, case_id): return self.session.get(PostpartumCase, case_id)
    def case_for_update(self, case_id):
        return self.session.scalar(select(PostpartumCase).where(PostpartumCase.id == case_id).with_for_update())
    def pause(self, pause_id): return self.session.get(PostpartumServicePause, pause_id)

    def list_cases(self, page, page_size, active, status, search):
        filters = []
        if active is not None: filters.append(PostpartumCase.is_active == active)
        if status is not None: filters.append(PostpartumCase.status == status)
        if search:
            term = f"%{search.strip().lower()}%"
            filters.append(or_(func.lower(PostpartumCase.case_number).like(term),
                               func.lower(PostpartumCase.name).like(term),
                               func.lower(PostpartumCase.current_room).like(term)))
        total = self.session.scalar(select(func.count()).select_from(PostpartumCase).where(*filters)) or 0
        rows = self.session.scalars(select(PostpartumCase).where(*filters).order_by(
            PostpartumCase.is_active.desc(), PostpartumCase.service_start_date.desc(),
            PostpartumCase.created_at.desc(), PostpartumCase.id).offset((page - 1) * page_size).limit(page_size))
        return list(rows), total

    @staticmethod
    def _meal_order(column):
        return case((column == "breakfast", 0), (column == "lunch", 1), else_=2)

    def room_history(self, case_id):
        return list(self.session.scalars(select(PostpartumRoomHistory).where(
            PostpartumRoomHistory.case_id == case_id).order_by(
            PostpartumRoomHistory.effective_date, self._meal_order(PostpartumRoomHistory.effective_meal),
            PostpartumRoomHistory.created_at, PostpartumRoomHistory.id)))

    def pauses(self, case_id):
        return list(self.session.scalars(select(PostpartumServicePause).where(
            PostpartumServicePause.case_id == case_id).order_by(
            PostpartumServicePause.start_date, self._meal_order(PostpartumServicePause.start_meal),
            PostpartumServicePause.id)))

    def restriction_group(self, group_id):
        return self.session.get(PostpartumRestrictionGroup, group_id)

    def restriction_group_name_exists(self, name, exclude_id=None):
        statement = select(PostpartumRestrictionGroup.id).where(
            func.lower(func.btrim(PostpartumRestrictionGroup.name)) == name.strip().lower()
        )
        if exclude_id is not None:
            statement = statement.where(PostpartumRestrictionGroup.id != exclude_id)
        return self.session.scalar(statement.limit(1)) is not None

    def list_restriction_groups(self, page, page_size, active, search):
        ingredient_count = select(func.count()).select_from(PostpartumRestrictionGroupIngredient).where(
            PostpartumRestrictionGroupIngredient.restriction_group_id == PostpartumRestrictionGroup.id
        ).correlate(PostpartumRestrictionGroup).scalar_subquery()
        dish_count = select(func.count()).select_from(PostpartumRestrictionGroupDish).where(
            PostpartumRestrictionGroupDish.restriction_group_id == PostpartumRestrictionGroup.id
        ).correlate(PostpartumRestrictionGroup).scalar_subquery()
        filters = []
        if active is not None:
            filters.append(PostpartumRestrictionGroup.is_active == active)
        if search:
            term = f"%{search.strip().lower()}%"
            filters.append(func.lower(PostpartumRestrictionGroup.name).like(term))
        total = self.session.scalar(select(func.count()).select_from(PostpartumRestrictionGroup).where(*filters)) or 0
        statement = select(
            PostpartumRestrictionGroup.id, PostpartumRestrictionGroup.name, PostpartumRestrictionGroup.color,
            PostpartumRestrictionGroup.notes, PostpartumRestrictionGroup.is_active,
            PostpartumRestrictionGroup.created_at, PostpartumRestrictionGroup.updated_at,
            PostpartumRestrictionGroup.created_by, PostpartumRestrictionGroup.updated_by,
            ingredient_count.label("ingredient_count"), dish_count.label("dish_count"),
        ).where(*filters).order_by(
            PostpartumRestrictionGroup.is_active.desc(), func.lower(PostpartumRestrictionGroup.name),
            PostpartumRestrictionGroup.id,
        ).offset((page - 1) * page_size).limit(page_size)
        return [dict(row) for row in self.session.execute(statement).mappings()], total

    def restriction_ingredients(self, group_id):
        statement = select(Ingredient.id, Ingredient.code, Ingredient.name, Ingredient.is_active).join(
            PostpartumRestrictionGroupIngredient,
            PostpartumRestrictionGroupIngredient.ingredient_id == Ingredient.id,
        ).where(PostpartumRestrictionGroupIngredient.restriction_group_id == group_id).order_by(
            *natural_code_order(Ingredient.code), Ingredient.id,
        )
        return [dict(row) for row in self.session.execute(statement).mappings()]

    def restriction_dishes(self, group_id):
        statement = select(Dish.id, Dish.code, Dish.name, Dish.is_active).join(
            PostpartumRestrictionGroupDish, PostpartumRestrictionGroupDish.dish_id == Dish.id,
        ).where(PostpartumRestrictionGroupDish.restriction_group_id == group_id).order_by(
            *natural_code_order(Dish.code), Dish.id,
        )
        return [dict(row) for row in self.session.execute(statement).mappings()]

    def restriction_ingredient_ids(self, group_id):
        return set(self.session.scalars(select(PostpartumRestrictionGroupIngredient.ingredient_id).where(
            PostpartumRestrictionGroupIngredient.restriction_group_id == group_id
        )))

    def restriction_dish_ids(self, group_id):
        return set(self.session.scalars(select(PostpartumRestrictionGroupDish.dish_id).where(
            PostpartumRestrictionGroupDish.restriction_group_id == group_id
        )))

    def ingredient_models(self, ids):
        if not ids:
            return {}
        return {item.id: item for item in self.session.scalars(select(Ingredient).where(Ingredient.id.in_(ids)))}

    def dish_models(self, ids):
        if not ids:
            return {}
        return {item.id: item for item in self.session.scalars(select(Dish).where(Dish.id.in_(ids)))}

    def replace_restriction_ingredients(self, group_id, existing_ids, requested_ids):
        removed = existing_ids - requested_ids
        if removed:
            self.session.execute(delete(PostpartumRestrictionGroupIngredient).where(
                PostpartumRestrictionGroupIngredient.restriction_group_id == group_id,
                PostpartumRestrictionGroupIngredient.ingredient_id.in_(removed),
            ))
        for ingredient_id in requested_ids - existing_ids:
            self.add(PostpartumRestrictionGroupIngredient(restriction_group_id=group_id, ingredient_id=ingredient_id))

    def replace_restriction_dishes(self, group_id, existing_ids, requested_ids):
        removed = existing_ids - requested_ids
        if removed:
            self.session.execute(delete(PostpartumRestrictionGroupDish).where(
                PostpartumRestrictionGroupDish.restriction_group_id == group_id,
                PostpartumRestrictionGroupDish.dish_id.in_(removed),
            ))
        for dish_id in requested_ids - existing_ids:
            self.add(PostpartumRestrictionGroupDish(restriction_group_id=group_id, dish_id=dish_id))
