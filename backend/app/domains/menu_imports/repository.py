import uuid

from sqlalchemy import delete, func, select

from app.domains.dishes.models import Dish
from app.domains.menu_imports.models import MenuImportBatch, MenuImportLine
from app.domains.menus.models import Menu
from app.domains.users.models import User


class MenuImportRepository:
    def __init__(self, session):
        self.session = session

    def add(self, value) -> None:
        self.session.add(value)

    def batch(self, batch_id: uuid.UUID, *, for_update: bool = False):
        statement = select(MenuImportBatch).where(MenuImportBatch.id == batch_id)
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def active_duplicate(self, source_hash: str, sheet_name: str, created_by: uuid.UUID):
        return self.session.scalar(select(MenuImportBatch).where(
            MenuImportBatch.source_hash == source_hash,
            MenuImportBatch.sheet_name == sheet_name,
            MenuImportBatch.created_by == created_by,
            MenuImportBatch.status.in_(("REVIEW_REQUIRED", "READY")),
        ).order_by(MenuImportBatch.created_at.desc(), MenuImportBatch.id))

    def lines(self, batch_id: uuid.UUID):
        return list(self.session.scalars(select(MenuImportLine).where(
            MenuImportLine.batch_id == batch_id,
        ).order_by(
            MenuImportLine.menu_date,
            MenuImportLine.meal_sort_order,
            MenuImportLine.column_sort_order,
            MenuImportLine.source_row,
            MenuImportLine.source_column,
            MenuImportLine.id,
        )))

    def line(self, batch_id: uuid.UUID, line_id: uuid.UUID, *, for_update: bool = False):
        statement = select(MenuImportLine).where(
            MenuImportLine.batch_id == batch_id, MenuImportLine.id == line_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def dishes(self, dish_ids: set[uuid.UUID]):
        if not dish_ids:
            return {}
        values = self.session.scalars(select(Dish).where(Dish.id.in_(dish_ids)))
        return {value.id: value for value in values}

    def active_dish(self, dish_id: uuid.UUID):
        return self.session.scalar(select(Dish).where(Dish.id == dish_id, Dish.is_active.is_(True)))

    def all_dishes(self):
        return list(self.session.scalars(select(Dish).order_by(Dish.id)))

    def finalized_menu(self, menu_id: uuid.UUID):
        return self.session.get(Menu, menu_id)

    def review_count(self, batch_id: uuid.UUID) -> int:
        return self.session.scalar(select(func.count()).select_from(MenuImportLine).where(
            MenuImportLine.batch_id == batch_id, MenuImportLine.review_required.is_(True),
        )) or 0

    def listing(self, page: int, page_size: int):
        filters = [MenuImportBatch.status.in_(("REVIEW_REQUIRED", "READY"))]
        total = self.session.scalar(select(func.count()).select_from(MenuImportBatch).where(*filters)) or 0
        rows = self.session.execute(select(MenuImportBatch, User.display_name).join(
            User, User.id == MenuImportBatch.created_by,
        ).where(*filters).order_by(
            MenuImportBatch.updated_at.desc(), MenuImportBatch.id,
        ).offset((page - 1) * page_size).limit(page_size)).all()
        return rows, total

    def user_display_name(self, user_id: uuid.UUID) -> str | None:
        return self.session.scalar(select(User.display_name).where(User.id == user_id))

    def delete_batch(self, batch_id: uuid.UUID) -> None:
        self.session.execute(delete(MenuImportBatch).where(MenuImportBatch.id == batch_id))
