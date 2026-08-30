from __future__ import annotations

import uuid

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session

from app.domains.suppliers.models import Supplier


class SupplierRepository:
    def __init__(self, session: Session) -> None: self.session = session
    def add(self, supplier: Supplier) -> None: self.session.add(supplier)
    def get(self, supplier_id: uuid.UUID) -> Supplier | None: return self.session.get(Supplier, supplier_id)
    def code_exists(self, code: str, exclude_id: uuid.UUID | None = None) -> bool:
        statement = select(Supplier.id).where(func.lower(Supplier.code) == code.lower())
        if exclude_id: statement = statement.where(Supplier.id != exclude_id)
        return self.session.scalar(statement.limit(1)) is not None
    def next_sort_order(self) -> int:
        return (self.session.scalar(select(func.max(Supplier.sort_order))) or 0) + 1
    def ordered_ids(self) -> list[uuid.UUID]:
        statement = select(Supplier.id).order_by(Supplier.sort_order, Supplier.code, Supplier.id)
        return list(self.session.scalars(statement))
    def list(self, page: int, page_size: int, active: bool | None, search: str | None) -> tuple[list[Supplier], int]:
        filters = []
        if active is not None: filters.append(Supplier.is_active == active)
        if search:
            term = f"%{search.strip().lower()}%"
            filters.append(or_(func.lower(Supplier.code).like(term), func.lower(Supplier.name).like(term)))
        total = self.session.scalar(select(func.count()).select_from(Supplier).where(*filters)) or 0
        statement = select(Supplier).where(*filters).order_by(Supplier.sort_order, Supplier.code, Supplier.id).offset((page-1)*page_size).limit(page_size)
        return list(self.session.scalars(statement)), total
    def reorder(self, supplier_ids: list[uuid.UUID], actor_id: uuid.UUID) -> None:
        positions = {supplier_id: position for position, supplier_id in enumerate(supplier_ids, start=1)}
        statement = (
            update(Supplier)
            .where(Supplier.id.in_(supplier_ids))
            .values(
                sort_order=case(positions, value=Supplier.id),
                updated_by=actor_id,
                updated_at=func.now(),
            )
        )
        self.session.execute(statement)
    def has_references(self, supplier_id: uuid.UUID) -> bool:
        from app.domains.ingredients.models import Ingredient, IngredientPriceHistory
        ingredient = self.session.scalar(select(Ingredient.id).where(Ingredient.primary_supplier_id == supplier_id).limit(1))
        history = self.session.scalar(select(IngredientPriceHistory.id).where(IngredientPriceHistory.supplier_id == supplier_id).limit(1))
        return ingredient is not None or history is not None
    def delete(self, supplier: Supplier) -> None: self.session.delete(supplier)
