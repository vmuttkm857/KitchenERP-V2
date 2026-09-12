import uuid

from sqlalchemy import case, delete, func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.domains.dishes.models import Dish
from app.domains.ingredients.models import Ingredient
from app.domains.postpartum.models import (
    PostpartumCase, PostpartumCaseRestrictionGroup, PostpartumMenuMealMapping, PostpartumMenuSource,
    PostpartumRestrictionGroup, PostpartumRestrictionGroupDish, PostpartumRestrictionGroupIngredient,
    PostpartumRoomHistory, PostpartumServicePause, PostpartumReplacementGroup,
    PostpartumConflictHandling,
)
from app.domains.postpartum.meals import MEAL_ORDER
from app.domains.menus.models import Menu, MenuDay, MenuDish, MenuMealType
from app.domains.recipes.models import DishIngredient
from app.shared.sorting import natural_code_order


class PostpartumRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, value): self.session.add(value)
    def delete(self, value): self.session.delete(value)
    def case(self, case_id): return self.session.get(PostpartumCase, case_id)
    def case_models(self, case_ids):
        if not case_ids:
            return []
        return list(self.session.scalars(select(PostpartumCase).where(PostpartumCase.id.in_(case_ids))))
    def case_for_update(self, case_id):
        return self.session.scalar(select(PostpartumCase).where(PostpartumCase.id == case_id).with_for_update())
    def pause(self, pause_id): return self.session.get(PostpartumServicePause, pause_id)

    def menu_source_for_update(self, source_id):
        return self.session.scalar(select(PostpartumMenuSource).where(
            PostpartumMenuSource.id == source_id).with_for_update())

    def menu_source(self, source_id):
        return self.session.get(PostpartumMenuSource, source_id)

    def menu_source_by_menu(self, menu_id):
        return self.session.scalar(select(PostpartumMenuSource).where(PostpartumMenuSource.menu_id == menu_id))

    def menu_sources(self, from_date=None, to_date=None):
        statement = select(PostpartumMenuSource, Menu).join(Menu, Menu.id == PostpartumMenuSource.menu_id)
        if from_date is not None:
            statement = statement.where(Menu.end_date >= from_date)
        if to_date is not None:
            statement = statement.where(Menu.start_date <= to_date)
        return list(self.session.execute(statement.order_by(
            Menu.start_date, Menu.end_date, func.lower(Menu.name), PostpartumMenuSource.id,
        )).all())

    def overlapping_menu_sources(self, start_date, end_date, exclude_source_id=None):
        statement = select(PostpartumMenuSource, Menu).join(
            Menu, Menu.id == PostpartumMenuSource.menu_id,
        ).where(Menu.start_date <= end_date, Menu.end_date >= start_date)
        if exclude_source_id is not None:
            statement = statement.where(PostpartumMenuSource.id != exclude_source_id)
        return list(self.session.execute(statement).all())

    def menu(self, menu_id): return self.session.get(Menu, menu_id)

    def menu_meal_types(self, ids):
        if not ids:
            return {}
        return {item.id: item for item in self.session.scalars(
            select(MenuMealType).where(MenuMealType.id.in_(ids))
        )}

    def menu_source_mappings(self, source_id):
        statement = select(PostpartumMenuMealMapping, MenuMealType).join(
            MenuMealType, MenuMealType.id == PostpartumMenuMealMapping.menu_meal_type_id,
        ).where(PostpartumMenuMealMapping.menu_source_id == source_id)
        return list(self.session.execute(statement).all())

    def replace_menu_source_mappings(self, source_id, mappings):
        self.session.execute(delete(PostpartumMenuMealMapping).where(
            PostpartumMenuMealMapping.menu_source_id == source_id,
        ))
        for postpartum_meal, menu_meal_type_id in mappings:
            self.add(PostpartumMenuMealMapping(
                menu_source_id=source_id,
                postpartum_meal=postpartum_meal,
                menu_meal_type_id=menu_meal_type_id,
            ))

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

    def case_restriction_groups(self, case_ids):
        if not case_ids:
            return {}
        statement = select(
            PostpartumCaseRestrictionGroup.case_id,
            PostpartumRestrictionGroup.id,
            PostpartumRestrictionGroup.name,
            PostpartumRestrictionGroup.color,
            PostpartumRestrictionGroup.is_active,
        ).join(
            PostpartumRestrictionGroup,
            PostpartumRestrictionGroup.id == PostpartumCaseRestrictionGroup.restriction_group_id,
        ).where(PostpartumCaseRestrictionGroup.case_id.in_(case_ids)).order_by(
            PostpartumCaseRestrictionGroup.case_id,
            func.lower(PostpartumRestrictionGroup.name),
            PostpartumRestrictionGroup.id,
        )
        grouped = {case_id: [] for case_id in case_ids}
        for row in self.session.execute(statement).mappings():
            grouped[row["case_id"]].append({
                "id": row["id"], "name": row["name"], "color": row["color"],
                "is_active": row["is_active"],
            })
        return grouped

    def case_restriction_group_ids(self, case_id):
        return set(self.session.scalars(select(PostpartumCaseRestrictionGroup.restriction_group_id).where(
            PostpartumCaseRestrictionGroup.case_id == case_id,
        )))

    def restriction_group_models(self, ids):
        if not ids:
            return {}
        return {item.id: item for item in self.session.scalars(
            select(PostpartumRestrictionGroup).where(PostpartumRestrictionGroup.id.in_(ids))
        )}

    def replace_case_restriction_groups(self, case_id, existing_ids, requested_ids):
        removed = existing_ids - requested_ids
        if removed:
            self.session.execute(delete(PostpartumCaseRestrictionGroup).where(
                PostpartumCaseRestrictionGroup.case_id == case_id,
                PostpartumCaseRestrictionGroup.restriction_group_id.in_(removed),
            ))
        for group_id in requested_ids - existing_ids:
            self.add(PostpartumCaseRestrictionGroup(case_id=case_id, restriction_group_id=group_id))

    @staticmethod
    def _meal_order(column):
        return case(*((column == meal, order) for meal, order in MEAL_ORDER.items()), else_=len(MEAL_ORDER))

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

    def conflict_sources_range(self, start_date, end_date):
        statement = select(
            PostpartumMenuSource.id.label("source_id"),
            Menu.id.label("menu_id"), Menu.name.label("menu_name"),
            Menu.start_date, Menu.end_date, Menu.is_active.label("menu_is_active"),
            PostpartumMenuMealMapping.postpartum_meal,
            PostpartumMenuMealMapping.menu_meal_type_id.label("mapped_menu_meal_type_id"),
            MenuMealType.id.label("menu_meal_type_id"), MenuMealType.name.label("menu_meal_type_name"),
            MenuMealType.sort_order.label("menu_meal_type_sort_order"),
            MenuMealType.is_active.label("menu_meal_type_is_active"),
            MenuMealType.menu_id.label("menu_meal_type_menu_id"),
        ).join(
            Menu, Menu.id == PostpartumMenuSource.menu_id,
        ).outerjoin(
            PostpartumMenuMealMapping,
            PostpartumMenuMealMapping.menu_source_id == PostpartumMenuSource.id,
        ).outerjoin(
            MenuMealType, MenuMealType.id == PostpartumMenuMealMapping.menu_meal_type_id,
        ).where(
            Menu.start_date <= end_date, Menu.end_date >= start_date,
        ).order_by(
            Menu.start_date, Menu.end_date, func.lower(Menu.name), PostpartumMenuSource.id,
            self._meal_order(PostpartumMenuMealMapping.postpartum_meal),
        )
        return [dict(row) for row in self.session.execute(statement).mappings()]

    def conflict_menu_rows_range(self, menu_ids, start_date, end_date):
        if not menu_ids:
            return []
        statement = select(
            MenuDay.id.label("menu_day_id"), MenuDay.menu_id,
            MenuDay.menu_meal_type_id, MenuDay.menu_date,
            MenuDish.id.label("menu_dish_id"), MenuDish.sort_order,
            Dish.id.label("dish_id"), Dish.code.label("dish_code"), Dish.name.label("dish_name"),
            Dish.is_active.label("dish_is_active"),
        ).outerjoin(
            MenuDish, MenuDish.menu_day_id == MenuDay.id,
        ).outerjoin(
            Dish, Dish.id == MenuDish.dish_id,
        ).where(
            MenuDay.menu_id.in_(menu_ids),
            MenuDay.menu_date >= start_date,
            MenuDay.menu_date <= end_date,
        ).order_by(
            MenuDay.menu_date, MenuDay.menu_id, MenuDay.menu_meal_type_id,
            MenuDish.sort_order, MenuDish.id,
        )
        return [dict(row) for row in self.session.execute(statement).mappings()]

    def conflict_case_candidates_range(self, start_date, end_date):
        statement = select(PostpartumCase).where(
            PostpartumCase.is_active.is_(True),
            PostpartumCase.service_start_date <= end_date,
            or_(PostpartumCase.service_end_date.is_(None), PostpartumCase.service_end_date >= start_date),
        ).order_by(
            func.lower(PostpartumCase.case_number), func.lower(PostpartumCase.name), PostpartumCase.id,
        )
        return list(self.session.scalars(statement))

    def conflict_pauses(self, case_ids):
        if not case_ids:
            return []
        statement = select(PostpartumServicePause).where(
            PostpartumServicePause.case_id.in_(case_ids),
        ).order_by(
            PostpartumServicePause.case_id, PostpartumServicePause.start_date,
            self._meal_order(PostpartumServicePause.start_meal), PostpartumServicePause.id,
        )
        return list(self.session.scalars(statement))

    def conflict_case_groups(self, case_ids):
        if not case_ids:
            return []
        statement = select(
            PostpartumCaseRestrictionGroup.case_id,
            PostpartumRestrictionGroup.id.label("restriction_group_id"),
            PostpartumRestrictionGroup.name, PostpartumRestrictionGroup.color,
            PostpartumRestrictionGroup.notes, PostpartumRestrictionGroup.is_active,
        ).join(
            PostpartumRestrictionGroup,
            PostpartumRestrictionGroup.id == PostpartumCaseRestrictionGroup.restriction_group_id,
        ).where(
            PostpartumCaseRestrictionGroup.case_id.in_(case_ids),
        ).order_by(
            PostpartumCaseRestrictionGroup.case_id,
            func.lower(PostpartumRestrictionGroup.name), PostpartumRestrictionGroup.id,
        )
        return [dict(row) for row in self.session.execute(statement).mappings()]

    def conflict_group_dishes(self, group_ids):
        if not group_ids:
            return []
        statement = select(
            PostpartumRestrictionGroupDish.restriction_group_id,
            Dish.id, Dish.code, Dish.name, Dish.is_active,
        ).join(Dish, Dish.id == PostpartumRestrictionGroupDish.dish_id).where(
            PostpartumRestrictionGroupDish.restriction_group_id.in_(group_ids),
        ).order_by(
            PostpartumRestrictionGroupDish.restriction_group_id,
            *natural_code_order(Dish.code), Dish.id,
        )
        return [dict(row) for row in self.session.execute(statement).mappings()]

    def conflict_group_ingredients(self, group_ids):
        if not group_ids:
            return []
        statement = select(
            PostpartumRestrictionGroupIngredient.restriction_group_id,
            Ingredient.id, Ingredient.code, Ingredient.name, Ingredient.is_active,
        ).join(Ingredient, Ingredient.id == PostpartumRestrictionGroupIngredient.ingredient_id).where(
            PostpartumRestrictionGroupIngredient.restriction_group_id.in_(group_ids),
        ).order_by(
            PostpartumRestrictionGroupIngredient.restriction_group_id,
            *natural_code_order(Ingredient.code), Ingredient.id,
        )
        return [dict(row) for row in self.session.execute(statement).mappings()]

    def conflict_recipe_ingredients(self, dish_ids):
        if not dish_ids:
            return []
        statement = select(
            DishIngredient.dish_id,
            Ingredient.id, Ingredient.code, Ingredient.name, Ingredient.is_active,
        ).join(Ingredient, Ingredient.id == DishIngredient.ingredient_id).where(
            DishIngredient.dish_id.in_(dish_ids),
        ).order_by(
            DishIngredient.dish_id, DishIngredient.sort_order, DishIngredient.id,
        )
        return [dict(row) for row in self.session.execute(statement).mappings()]

    def replacement_group(self, group_id, for_update=False):
        statement = select(PostpartumReplacementGroup).where(PostpartumReplacementGroup.id == group_id)
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def replacement_groups(self, target_date, postpartum_meal=None):
        statement = select(PostpartumReplacementGroup).where(
            PostpartumReplacementGroup.target_date == target_date,
        )
        if postpartum_meal is not None:
            statement = statement.where(PostpartumReplacementGroup.postpartum_meal == postpartum_meal)
        return list(self.session.scalars(statement.order_by(
            PostpartumReplacementGroup.postpartum_meal, PostpartumReplacementGroup.id,
        )))

    def conflict_handling(self, handling_id, for_update=False):
        statement = select(PostpartumConflictHandling).where(PostpartumConflictHandling.id == handling_id)
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def conflict_handlings(self, target_date, postpartum_meal=None, for_update=False):
        statement = select(PostpartumConflictHandling).where(
            PostpartumConflictHandling.target_date == target_date,
        )
        if postpartum_meal is not None:
            statement = statement.where(PostpartumConflictHandling.postpartum_meal == postpartum_meal)
        statement = statement.order_by(
            PostpartumConflictHandling.postpartum_meal,
            PostpartumConflictHandling.replacement_group_id,
            PostpartumConflictHandling.id,
        )
        if for_update:
            statement = statement.with_for_update()
        return list(self.session.scalars(statement))

    def conflict_handlings_for_items(self, items, for_update=False):
        if not items:
            return []
        keys = [(item["case_id"], item["original_menu_dish_id"]) for item in items]
        statement = select(PostpartumConflictHandling).where(tuple_(
            PostpartumConflictHandling.case_id, PostpartumConflictHandling.original_menu_dish_id,
        ).in_(keys))
        if for_update:
            statement = statement.with_for_update()
        return list(self.session.scalars(statement))

    def replacement_candidate_dishes(self, page, page_size, search=None, category_id=None):
        filters = [Dish.is_active.is_(True)]
        if category_id is not None:
            filters.append(Dish.category_id == category_id)
        if search:
            term = f"%{search.strip().lower()}%"
            filters.append(or_(func.lower(Dish.code).like(term), func.lower(Dish.name).like(term)))
        total = self.session.scalar(select(func.count()).select_from(Dish).where(*filters)) or 0
        rows = self.session.execute(select(
            Dish.id, Dish.code, Dish.name, Dish.is_active,
        ).where(*filters).order_by(
            *natural_code_order(Dish.code), Dish.id,
        ).offset((page - 1) * page_size).limit(page_size)).mappings()
        return [dict(row) for row in rows], total

    def menu_dish_identities(self, menu_dish_ids):
        if not menu_dish_ids:
            return {}
        rows = self.session.execute(select(
            MenuDish.id.label("menu_dish_id"), MenuDish.dish_id,
            MenuDay.menu_date, MenuDay.menu_meal_type_id,
            Dish.code.label("dish_code"), Dish.name.label("dish_name"),
            Dish.is_active.label("dish_is_active"),
        ).join(MenuDay, MenuDay.id == MenuDish.menu_day_id).join(
            Dish, Dish.id == MenuDish.dish_id,
        ).where(MenuDish.id.in_(menu_dish_ids))).mappings()
        return {row["menu_dish_id"]: dict(row) for row in rows}
