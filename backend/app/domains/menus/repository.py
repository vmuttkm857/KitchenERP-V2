import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domains.categories.models import DishCategory, MenuCategory
from app.domains.dishes.models import Dish
from app.domains.menus.models import Menu, MenuDay, MenuDish, MenuMealType


class MenuRepository:
    def __init__(self, session: Session): self.session = session
    def add(self, value): self.session.add(value)
    def delete(self, value): self.session.delete(value)
    def menu_model(self, menu_id): return self.session.get(Menu, menu_id)
    def category(self, category_id): return self.session.get(MenuCategory, category_id)
    def meal_type(self, meal_type_id): return self.session.get(MenuMealType, meal_type_id)
    def dish_models(self, ids: set[uuid.UUID]):
        if not ids: return {}
        return {row.id: row for row in self.session.scalars(select(Dish).where(Dish.id.in_(ids)))}
    def _menu_view(self):
        return select(Menu.id, Menu.name, Menu.start_date, Menu.end_date, Menu.category_id,
                      MenuCategory.name.label("category_name"), Menu.notes, Menu.is_active,
                      Menu.created_at, Menu.updated_at, Menu.created_by, Menu.updated_by).outerjoin(MenuCategory, MenuCategory.id == Menu.category_id)
    def menu_view(self, menu_id): return self.session.execute(self._menu_view().where(Menu.id == menu_id)).mappings().one_or_none()
    def list(self, page, page_size, active, search, category_id):
        filters=[]
        if active is not None: filters.append(Menu.is_active == active)
        if category_id: filters.append(Menu.category_id == category_id)
        if search: filters.append(func.lower(Menu.name).like(f"%{search.strip().lower()}%"))
        total=self.session.scalar(select(func.count()).select_from(Menu).where(*filters)) or 0
        rows=self.session.execute(self._menu_view().where(*filters).order_by(Menu.start_date.desc(), func.lower(Menu.name), Menu.id).offset((page-1)*page_size).limit(page_size)).mappings()
        return [dict(row) for row in rows], total
    def meal_types(self, menu_id):
        return list(self.session.scalars(select(MenuMealType).where(MenuMealType.menu_id == menu_id).order_by(MenuMealType.sort_order, MenuMealType.id)))
    def meal_name_exists(self, menu_id, name, exclude=None):
        stmt=select(MenuMealType.id).where(MenuMealType.menu_id==menu_id, func.lower(MenuMealType.name)==name.lower())
        if exclude: stmt=stmt.where(MenuMealType.id != exclude)
        return self.session.scalar(stmt.limit(1)) is not None
    def days(self, menu_id):
        return list(self.session.scalars(select(MenuDay).where(MenuDay.menu_id==menu_id)))
    def details(self, day_ids: set[uuid.UUID]):
        if not day_ids: return []
        return list(self.session.scalars(select(MenuDish).where(MenuDish.menu_day_id.in_(day_ids)).order_by(MenuDish.sort_order, MenuDish.id)))
    def aggregate_rows(self, menu_id):
        return list(self.session.execute(select(
            MenuDay.id.label("menu_day_id"), MenuDay.menu_date, MenuDay.menu_meal_type_id, MenuDay.notes.label("slot_notes"),
            MenuDish.id.label("menu_dish_id"), MenuDish.dish_id, Dish.code.label("dish_code"), Dish.name.label("dish_name"),
            DishCategory.name.label("dish_category_name"), MenuDish.diner_count, MenuDish.notes, MenuDish.sort_order,
            MenuDish.created_by, MenuDish.updated_by,
        ).outerjoin(MenuDish, MenuDish.menu_day_id==MenuDay.id).outerjoin(Dish, Dish.id==MenuDish.dish_id)
         .outerjoin(DishCategory, DishCategory.id==Dish.category_id).where(MenuDay.menu_id==menu_id)
         .order_by(MenuDay.menu_date, MenuDay.menu_meal_type_id, MenuDish.sort_order, MenuDish.id)).mappings())
    def has_children(self, menu_id):
        return self.session.scalar(select(MenuMealType.id).where(MenuMealType.menu_id==menu_id).limit(1)) is not None
    def meal_type_has_days(self, meal_type_id):
        return self.session.scalar(select(MenuDay.id).where(MenuDay.menu_meal_type_id==meal_type_id).limit(1)) is not None
    def source_rows(self, menu_id, menu_date):
        return list(self.session.execute(select(MenuDay, MenuMealType, MenuDish, Dish)
            .join(MenuMealType, MenuMealType.id==MenuDay.menu_meal_type_id)
            .outerjoin(MenuDish, MenuDish.menu_day_id==MenuDay.id).outerjoin(Dish, Dish.id==MenuDish.dish_id)
            .where(MenuDay.menu_id==menu_id, MenuDay.menu_date==menu_date)
            .order_by(MenuMealType.sort_order, MenuDish.sort_order, MenuDish.id)).all())
