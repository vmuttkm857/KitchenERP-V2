import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.auth.service import AuthService
from app.domains.audit.service import AuditLogService, audit_snapshot
from app.domains.categories.exceptions import CategoryInUseError, CategoryNameExistsError, CategoryNotFoundError, InvalidCategoryColorError
from app.domains.categories.repository import CategoryRepository
from app.domains.categories.schemas import CategoryCreate, CategoryKind, CategoryUpdate


class CategoryService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = CategoryRepository(session)
        self.audit = AuditLogService(session)

    @staticmethod
    def _validate_color_kind(kind, data):
        if kind != "dish" and "background_color" in data.model_fields_set:
            raise InvalidCategoryColorError()

    @staticmethod
    def _audit_fields(kind):
        return ("name", "sort_order", "is_active") + (("background_color",) if kind == "dish" else ())

    def create(self, kind: CategoryKind, data: CategoryCreate, actor_id: uuid.UUID) -> Any:
        self._validate_color_kind(kind, data)
        name = data.name.strip()
        if self.repository.name_exists(kind, name):
            raise CategoryNameExistsError()
        model = self.repository.model_for(kind)
        category = model(id=uuid.uuid4(), name=name, sort_order=data.sort_order, created_by=actor_id, updated_by=actor_id)
        if kind == "dish":
            category.background_color = data.background_color
        self.repository.add(category)
        self.audit.record(actor_id=actor_id, action="category_create", entity_type=f"{kind}_category",
                          entity_id=category.id, entity_label=category.name,
                          after_data=audit_snapshot(category, *self._audit_fields(kind)))
        self._commit_unique()
        self.session.refresh(category)
        return category

    def get(self, kind: CategoryKind, category_id: uuid.UUID) -> Any:
        category = self.repository.get(kind, category_id)
        if category is None:
            raise CategoryNotFoundError()
        return category

    def list(self, kind: CategoryKind, page: int, page_size: int, active: bool | None) -> tuple[list[Any], int]:
        return self.repository.list(kind, page, page_size, active)

    def update(self, kind: CategoryKind, category_id: uuid.UUID, data: CategoryUpdate, actor_id: uuid.UUID) -> Any:
        self._validate_color_kind(kind, data)
        category = self.get(kind, category_id)
        before = audit_snapshot(category, *self._audit_fields(kind))
        if data.name is not None:
            name = data.name.strip()
            if self.repository.name_exists(kind, name, category_id):
                raise CategoryNameExistsError()
            category.name = name
        if data.sort_order is not None:
            category.sort_order = data.sort_order
        if kind == "dish" and "background_color" in data.model_fields_set:
            category.background_color = data.background_color
        category.updated_by = actor_id
        action = "category_reorder" if data.sort_order is not None and data.name is None and "background_color" not in data.model_fields_set else "category_update"
        self.audit.record(actor_id=actor_id, action=action, entity_type=f"{kind}_category",
                          entity_id=category.id, entity_label=category.name, before_data=before,
                          after_data=audit_snapshot(category, *self._audit_fields(kind)))
        self._commit_unique()
        self.session.refresh(category)
        return category

    def set_active(self, kind: CategoryKind, category_id: uuid.UUID, active: bool, actor_id: uuid.UUID) -> Any:
        category = self.get(kind, category_id)
        before = audit_snapshot(category, *self._audit_fields(kind))
        category.is_active = active
        category.updated_by = actor_id
        self.audit.record(actor_id=actor_id, action="category_reactivate" if active else "category_deactivate",
                          entity_type=f"{kind}_category", entity_id=category.id, entity_label=category.name,
                          before_data=before, after_data=audit_snapshot(category, *self._audit_fields(kind)))
        self.session.commit()
        self.session.refresh(category)
        return category

    def hard_delete(self, kind: CategoryKind, category_id: uuid.UUID, actor_id: uuid.UUID, password: str) -> None:
        AuthService(self.session).verify_current_password(actor_id, password)
        category = self.get(kind, category_id)
        before = audit_snapshot(category, *self._audit_fields(kind))
        if self.repository.has_references(kind, category_id):
            raise CategoryInUseError()
        self.repository.delete(category)
        self.audit.record(actor_id=actor_id, action="category_hard_delete", entity_type=f"{kind}_category",
                          entity_id=category.id, entity_label=category.name, before_data=before)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise CategoryInUseError() from exc

    def _commit_unique(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise CategoryNameExistsError() from exc
