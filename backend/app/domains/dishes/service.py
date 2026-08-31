import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.auth.service import AuthService
from app.domains.audit.service import AuditLogService, audit_snapshot
from app.domains.dishes.exceptions import (
    DishCodeExistsError, DishIdentityExistsError, DishInUseError, DishNameExistsError,
    DishNotFoundError, InvalidDishCategoryError,
)
from app.domains.dishes.models import Dish
from app.domains.dishes.repository import DishRepository
from app.domains.dishes.schemas import DishCreate, DishUpdate


class DishService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = DishRepository(session)
        self.audit = AuditLogService(session)

    def get_model(self, dish_id: uuid.UUID) -> Dish:
        dish = self.repository.get_model(dish_id)
        if dish is None:
            raise DishNotFoundError()
        return dish

    def get(self, dish_id: uuid.UUID):
        view = self.repository.get_view(dish_id)
        if view is None:
            raise DishNotFoundError()
        return dict(view)

    def list(self, page: int, page_size: int, active: bool | None, search: str | None, category_id: uuid.UUID | None):
        return self.repository.list(page, page_size, active, search, category_id)

    def _validate_category(self, category_id: uuid.UUID | None) -> None:
        if category_id is None:
            return
        category = self.repository.category(category_id)
        if category is None or not category.is_active:
            raise InvalidDishCategoryError()

    def create(self, data: DishCreate, actor_id: uuid.UUID):
        code, name = data.code.strip().upper(), data.name.strip()
        if self.repository.code_exists(code): raise DishCodeExistsError()
        if self.repository.name_exists(name): raise DishNameExistsError()
        self._validate_category(data.category_id)
        dish = Dish(id=uuid.uuid4(), code=code, name=name, category_id=data.category_id, notes=data.notes,
                    created_by=actor_id, updated_by=actor_id)
        self.repository.add(dish)
        self.audit.record(actor_id=actor_id, action="dish_create", entity_type="dish", entity_id=dish.id,
                          entity_label=dish.name, after_data=audit_snapshot(dish, "code", "name", "category_id", "notes", "is_active"))
        self._commit_identity()
        return self.get(dish.id)

    def update(self, dish_id: uuid.UUID, data: DishUpdate, actor_id: uuid.UUID):
        dish = self.get_model(dish_id)
        before = audit_snapshot(dish, "code", "name", "category_id", "notes", "is_active")
        changes = data.model_dump(exclude_unset=True)
        code = changes.get("code", dish.code).strip().upper()
        name = changes.get("name", dish.name).strip()
        if self.repository.code_exists(code, dish_id): raise DishCodeExistsError()
        if self.repository.name_exists(name, dish_id): raise DishNameExistsError()
        if "category_id" in changes:
            self._validate_category(changes["category_id"])
        changes["code"], changes["name"] = code, name
        for field, value in changes.items():
            setattr(dish, field, value)
        dish.updated_by = actor_id
        self.audit.record(actor_id=actor_id, action="dish_update", entity_type="dish", entity_id=dish.id,
                          entity_label=dish.name, before_data=before,
                          after_data=audit_snapshot(dish, "code", "name", "category_id", "notes", "is_active"))
        self._commit_identity()
        return self.get(dish.id)

    def set_active(self, dish_id: uuid.UUID, active: bool, actor_id: uuid.UUID):
        dish = self.get_model(dish_id)
        before = audit_snapshot(dish, "code", "name", "is_active")
        dish.is_active, dish.updated_by = active, actor_id
        self.audit.record(actor_id=actor_id, action="dish_reactivate" if active else "dish_deactivate",
                          entity_type="dish", entity_id=dish.id, entity_label=dish.name,
                          before_data=before, after_data=audit_snapshot(dish, "code", "name", "is_active"))
        self.session.commit()
        return self.get(dish.id)

    def hard_delete(self, dish_id: uuid.UUID, actor_id: uuid.UUID, password: str) -> None:
        AuthService(self.session).verify_current_password(actor_id, password)
        dish = self.get_model(dish_id)
        before = audit_snapshot(dish, "code", "name", "category_id", "notes", "is_active")
        if self.repository.has_recipe(dish_id) or self.repository.has_menu_references(dish_id):
            raise DishInUseError()
        self.repository.delete(dish)
        self.audit.record(actor_id=actor_id, action="dish_hard_delete", entity_type="dish",
                          entity_id=dish.id, entity_label=dish.name, before_data=before)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise DishInUseError() from exc

    def _commit_identity(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            constraint = getattr(getattr(getattr(exc, "orig", None), "diag", None), "constraint_name", None)
            if constraint == "uq_dishes_code": raise DishCodeExistsError() from exc
            if constraint in {"uq_dishes_name", "uq_dishes_name_normalized"}: raise DishNameExistsError() from exc
            raise DishIdentityExistsError() from exc
