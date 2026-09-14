import uuid
from datetime import date

from sqlalchemy import delete as sa_delete, func, or_, select
from sqlalchemy.orm import Session

from app.domains.categories.models import DishCategory, MenuCategory
from app.domains.dishes.models import Dish
from app.domains.menus.models import Menu, MenuDay, MenuDish, MenuMealType, MenuMealTypeColumn


class MenuRepository:
    def __init__(self, session: Session): self.session = session
    def add(self, value): self.session.add(value)
    def delete(self, value): self.session.delete(value)
    def menu_model(self, menu_id, for_update=False):
        if not for_update: return self.session.get(Menu, menu_id)
        return self.session.scalar(select(Menu).where(Menu.id==menu_id).with_for_update())
    def category(self, category_id): return self.session.get(MenuCategory, category_id)
    def meal_type(self, meal_type_id): return self.session.get(MenuMealType, meal_type_id)
    def meal_type_column(self, column_id): return self.session.get(MenuMealTypeColumn, column_id)
    def dish_models(self, ids: set[uuid.UUID]):
        if not ids: return {}
        return {row.id: row for row in self.session.scalars(select(Dish).where(Dish.id.in_(ids)))}
    def meal_type_column_models(self, ids: set[uuid.UUID]):
        if not ids: return {}
        return {row.id:row for row in self.session.scalars(select(MenuMealTypeColumn).where(MenuMealTypeColumn.id.in_(ids)))}
    def _menu_view(self):
        return select(Menu.id, Menu.name, Menu.start_date, Menu.end_date, Menu.category_id,
                      MenuCategory.name.label("category_name"), Menu.notes, Menu.is_active,
                      Menu.created_at, Menu.updated_at, Menu.created_by, Menu.updated_by).outerjoin(MenuCategory, MenuCategory.id == Menu.category_id)
    def menu_view(self, menu_id): return self.session.execute(self._menu_view().where(Menu.id == menu_id)).mappings().one_or_none()
    def list(self, page, page_size, active, search, category_id, start_date=None, end_date=None):
        filters=[]
        if active is not None: filters.append(Menu.is_active == active)
        if category_id: filters.append(Menu.category_id == category_id)
        if search: filters.append(func.lower(Menu.name).like(f"%{search.strip().lower()}%"))
        if start_date is not None: filters.append(Menu.end_date >= start_date)
        if end_date is not None: filters.append(Menu.start_date <= end_date)
        total=self.session.scalar(select(func.count()).select_from(Menu).where(*filters)) or 0
        rows=self.session.execute(self._menu_view().where(*filters).order_by(Menu.start_date.desc(), func.lower(Menu.name), Menu.id).offset((page-1)*page_size).limit(page_size)).mappings()
        return [dict(row) for row in rows], total
    def meal_types(self, menu_id):
        return list(self.session.scalars(select(MenuMealType).where(MenuMealType.menu_id == menu_id).order_by(MenuMealType.sort_order, MenuMealType.id)))
    def meal_name_exists(self, menu_id, name, exclude=None):
        stmt=select(MenuMealType.id).where(MenuMealType.menu_id==menu_id, func.lower(MenuMealType.name)==name.lower())
        if exclude: stmt=stmt.where(MenuMealType.id != exclude)
        return self.session.scalar(stmt.limit(1)) is not None
    def meal_type_columns(self, meal_type_id):
        return list(self.session.scalars(select(MenuMealTypeColumn).where(
            MenuMealTypeColumn.menu_meal_type_id==meal_type_id).order_by(
            MenuMealTypeColumn.sort_order,MenuMealTypeColumn.id)))
    def menu_columns(self, menu_id):
        return list(self.session.scalars(select(MenuMealTypeColumn).join(MenuMealType).where(
            MenuMealType.menu_id==menu_id).order_by(MenuMealType.sort_order,
            MenuMealTypeColumn.sort_order,MenuMealTypeColumn.id)))
    def column_name_exists(self, meal_type_id, name, exclude=None):
        stmt=select(MenuMealTypeColumn.id).where(
            MenuMealTypeColumn.menu_meal_type_id==meal_type_id,
            func.lower(MenuMealTypeColumn.name)==name.lower())
        if exclude: stmt=stmt.where(MenuMealTypeColumn.id!=exclude)
        return self.session.scalar(stmt.limit(1)) is not None
    def days(self, menu_id):
        return list(self.session.scalars(select(MenuDay).where(MenuDay.menu_id==menu_id)))
    def details(self, day_ids: set[uuid.UUID], for_update=False):
        if not day_ids: return []
        statement=select(MenuDish).where(MenuDish.menu_day_id.in_(day_ids)).order_by(MenuDish.sort_order, MenuDish.id)
        if for_update:statement=statement.with_for_update()
        return list(self.session.scalars(statement))
    def menu_dish_position(self, menu_dish_id, for_update=False):
        statement=select(MenuDish,MenuDay).join(MenuDay,MenuDay.id==MenuDish.menu_day_id).where(MenuDish.id==menu_dish_id)
        if for_update: statement=statement.with_for_update()
        return self.session.execute(statement).first()
    def day_for_slot(self,menu_id,menu_date,meal_type_id,for_update=False):
        statement=select(MenuDay).where(MenuDay.menu_id==menu_id,MenuDay.menu_date==menu_date,
            MenuDay.menu_meal_type_id==meal_type_id)
        if for_update:statement=statement.with_for_update()
        return self.session.scalar(statement)
    def replace_menu_dish_positions(self,dishes,placements,actor_id):
        values=[]
        for dish in dishes:
            row={column.name:getattr(dish,column.name) for column in MenuDish.__table__.columns}
            day_id,column_id,sort_order=placements[dish.id]
            row.update(menu_day_id=day_id,menu_meal_type_column_id=column_id,
                sort_order=sort_order,updated_by=actor_id)
            row.pop("updated_at",None)
            values.append(row);self.session.expunge(dish)
        self.session.execute(sa_delete(MenuDish).where(MenuDish.id.in_([row["id"] for row in values])))
        self.session.flush()
        replacements=tuple(MenuDish(**row) for row in values)
        for replacement in replacements:self.session.add(replacement)
        self.session.flush()
        return replacements
    def aggregate_rows(self, menu_id):
        return list(self.session.execute(select(
            MenuDay.id.label("menu_day_id"), MenuDay.menu_date, MenuDay.menu_meal_type_id, MenuDay.notes.label("slot_notes"),
            MenuDish.id.label("menu_dish_id"), MenuDish.dish_id, MenuDish.menu_meal_type_column_id, Dish.code.label("dish_code"), Dish.name.label("dish_name"),
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
