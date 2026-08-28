import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.auth.service import AuthService
from app.domains.categories.exceptions import CategoryInUseError, CategoryNameExistsError, CategoryNotFoundError
from app.domains.categories.repository import CategoryRepository
from app.domains.categories.schemas import CategoryCreate, CategoryKind, CategoryUpdate


class CategoryService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = CategoryRepository(session)

    def create(self, kind: CategoryKind, data: CategoryCreate, actor_id: uuid.UUID) -> Any:
        name = data.name.strip()
        if self.repository.name_exists(kind, name):
            raise CategoryNameExistsError()
        model = self.repository.model_for(kind)
        category = model(name=name, sort_order=data.sort_order, created_by=actor_id, updated_by=actor_id)
        self.repository.add(category)
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
        category = self.get(kind, category_id)
        if data.name is not None:
            name = data.name.strip()
            if self.repository.name_exists(kind, name, category_id):
                raise CategoryNameExistsError()
            category.name = name
        if data.sort_order is not None:
            category.sort_order = data.sort_order
        category.updated_by = actor_id
        self._commit_unique()
        self.session.refresh(category)
        return category

    def set_active(self, kind: CategoryKind, category_id: uuid.UUID, active: bool, actor_id: uuid.UUID) -> Any:
        category = self.get(kind, category_id)
        category.is_active = active
        category.updated_by = actor_id
        self.session.commit()
        self.session.refresh(category)
        return category

    def hard_delete(self, kind: CategoryKind, category_id: uuid.UUID, actor_id: uuid.UUID, password: str) -> None:
        AuthService(self.session).verify_current_password(actor_id, password)
        category = self.get(kind, category_id)
        if self.repository.has_references(kind, category_id):
            raise CategoryInUseError()
        self.repository.delete(category)
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
