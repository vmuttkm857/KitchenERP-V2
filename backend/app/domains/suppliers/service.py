from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.auth.service import AuthService
from app.domains.suppliers.exceptions import InvalidSupplierOrderError, SupplierCodeExistsError, SupplierInUseError, SupplierNotFoundError
from app.domains.suppliers.models import Supplier
from app.domains.suppliers.repository import SupplierRepository
from app.domains.suppliers.schemas import SupplierCreate, SupplierUpdate


class SupplierService:
    def __init__(self, session: Session) -> None:
        self.session = session; self.repository = SupplierRepository(session)
    def get(self, supplier_id: uuid.UUID) -> Supplier:
        supplier = self.repository.get(supplier_id)
        if supplier is None: raise SupplierNotFoundError()
        return supplier
    def list(self, page: int, page_size: int, active: bool | None, search: str | None): return self.repository.list(page, page_size, active, search)
    def create(self, data: SupplierCreate, actor_id: uuid.UUID) -> Supplier:
        code = data.code.strip().upper()
        if self.repository.code_exists(code): raise SupplierCodeExistsError()
        supplier = Supplier(
            code=code,
            name=data.name.strip(),
            contact_person=data.contact_person,
            phone=data.phone,
            address=data.address,
            notes=data.notes,
            sort_order=self.repository.next_sort_order(),
            is_active=data.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self.repository.add(supplier); self._commit_unique(); self.session.refresh(supplier); return supplier
    def update(self, supplier_id: uuid.UUID, data: SupplierUpdate, actor_id: uuid.UUID) -> Supplier:
        supplier = self.get(supplier_id)
        changes = data.model_dump(exclude_unset=True)
        if "code" in changes:
            code = changes.pop("code").strip().upper()
            if self.repository.code_exists(code, supplier_id): raise SupplierCodeExistsError()
            supplier.code = code
        if "name" in changes: changes["name"] = changes["name"].strip()
        if changes.get("is_active") is None: changes.pop("is_active", None)
        for field, value in changes.items(): setattr(supplier, field, value)
        supplier.updated_by = actor_id; self._commit_unique(); self.session.refresh(supplier); return supplier
    def ordered_ids(self) -> list[uuid.UUID]:
        return self.repository.ordered_ids()
    def reorder(self, supplier_ids: list[uuid.UUID], actor_id: uuid.UUID) -> None:
        if len(supplier_ids) != len(set(supplier_ids)):
            raise InvalidSupplierOrderError("Supplier IDs must not contain duplicates")
        current_ids = self.repository.ordered_ids()
        if len(supplier_ids) != len(current_ids) or set(supplier_ids) != set(current_ids):
            raise InvalidSupplierOrderError("Supplier IDs must contain every supplier exactly once")
        try:
            self.repository.reorder(supplier_ids, actor_id)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
    def set_active(self, supplier_id: uuid.UUID, active: bool, actor_id: uuid.UUID) -> Supplier:
        supplier = self.get(supplier_id); supplier.is_active = active; supplier.updated_by = actor_id; self.session.commit(); self.session.refresh(supplier); return supplier
    def hard_delete(self, supplier_id: uuid.UUID, actor_id: uuid.UUID, password: str) -> None:
        AuthService(self.session).verify_current_password(actor_id, password)
        supplier = self.get(supplier_id)
        if self.repository.has_references(supplier_id): raise SupplierInUseError()
        self.repository.delete(supplier)
        try: self.session.commit()
        except IntegrityError as exc: self.session.rollback(); raise SupplierInUseError() from exc
    def _commit_unique(self) -> None:
        try: self.session.commit()
        except IntegrityError as exc: self.session.rollback(); raise SupplierCodeExistsError() from exc
