import uuid
from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.auth.service import AuthService
from app.domains.ingredients.exceptions import IngredientCodeExistsError, IngredientInUseError, IngredientNotFoundError, InvalidIngredientReferenceError
from app.domains.ingredients.models import Ingredient, IngredientPriceHistory
from app.domains.ingredients.repository import IngredientRepository
from app.domains.ingredients.schemas import IngredientCreate, IngredientUpdate


class IngredientService:
    def __init__(self, session: Session) -> None:
        self.session = session; self.repository = IngredientRepository(session)
    def get_model(self, ingredient_id: uuid.UUID) -> Ingredient:
        ingredient = self.repository.get_model(ingredient_id)
        if ingredient is None: raise IngredientNotFoundError()
        return ingredient
    def get(self, ingredient_id: uuid.UUID):
        view = self.repository.get_view(ingredient_id)
        if view is None: raise IngredientNotFoundError()
        return dict(view)
    def list(self, page: int, page_size: int, active: bool | None, search: str | None, category_id: uuid.UUID | None): return self.repository.list(page, page_size, active, search, category_id)
    def _validate_references(self, category_id: uuid.UUID, supplier_id: uuid.UUID | None) -> None:
        category = self.repository.category(category_id)
        if category is None or not category.is_active: raise InvalidIngredientReferenceError("Active category is required")
        if supplier_id is not None:
            supplier = self.repository.supplier(supplier_id)
            if supplier is None or not supplier.is_active: raise InvalidIngredientReferenceError("Supplier must be active")
    def create(self, data: IngredientCreate, actor_id: uuid.UUID):
        code = data.code.strip().upper()
        if self.repository.code_exists(code): raise IngredientCodeExistsError()
        self._validate_references(data.category_id, data.primary_supplier_id)
        ingredient = Ingredient(code=code, name=data.name.strip(), category_id=data.category_id, unit=data.unit.strip(), current_price=data.current_price, primary_supplier_id=data.primary_supplier_id, purchase_unit=data.purchase_unit, package_size=data.package_size, minimum_order_quantity=data.minimum_order_quantity, notes=data.notes, created_by=actor_id, updated_by=actor_id)
        self.repository.add(ingredient); self.session.flush()
        self.repository.add_history(IngredientPriceHistory(ingredient_id=ingredient.id, supplier_id=data.primary_supplier_id, price=data.current_price, unit=data.unit.strip(), effective_date=data.price_effective_date, notes=data.price_notes, created_by=actor_id))
        self._commit_unique(); return self.get(ingredient.id)
    def update(self, ingredient_id: uuid.UUID, data: IngredientUpdate, actor_id: uuid.UUID):
        ingredient = self.get_model(ingredient_id); changes = data.model_dump(exclude_unset=True)
        effective_date = changes.pop("price_effective_date", None); price_notes = changes.pop("price_notes", None)
        if "code" in changes:
            code = changes.pop("code").strip().upper()
            if self.repository.code_exists(code, ingredient_id): raise IngredientCodeExistsError()
            ingredient.code = code
        category_id = changes.get("category_id", ingredient.category_id)
        supplier_id = changes.get("primary_supplier_id", ingredient.primary_supplier_id)
        if "category_id" in changes or "primary_supplier_id" in changes: self._validate_references(category_id, supplier_id)
        price_changed = "current_price" in changes and changes["current_price"] != ingredient.current_price
        if "name" in changes: changes["name"] = changes["name"].strip()
        if "unit" in changes: changes["unit"] = changes["unit"].strip()
        for field, value in changes.items(): setattr(ingredient, field, value)
        ingredient.updated_by = actor_id
        if price_changed:
            self.repository.add_history(IngredientPriceHistory(ingredient_id=ingredient.id, supplier_id=ingredient.primary_supplier_id, price=ingredient.current_price, unit=ingredient.unit, effective_date=effective_date or date.today(), notes=price_notes, created_by=actor_id))
        self._commit_unique(); return self.get(ingredient.id)
    def set_active(self, ingredient_id: uuid.UUID, active: bool, actor_id: uuid.UUID):
        ingredient = self.get_model(ingredient_id); ingredient.is_active = active; ingredient.updated_by = actor_id; self.session.commit(); return self.get(ingredient_id)
    def price_history(self, ingredient_id: uuid.UUID): self.get_model(ingredient_id); return self.repository.price_history(ingredient_id)
    def hard_delete(self, ingredient_id: uuid.UUID, actor_id: uuid.UUID, password: str) -> None:
        AuthService(self.session).verify_current_password(actor_id, password)
        ingredient = self.get_model(ingredient_id)
        if self.repository.has_history(ingredient_id): raise IngredientInUseError()
        self.repository.delete(ingredient)
        try: self.session.commit()
        except IntegrityError as exc: self.session.rollback(); raise IngredientInUseError() from exc
    def _commit_unique(self) -> None:
        try: self.session.commit()
        except IntegrityError as exc: self.session.rollback(); raise IngredientCodeExistsError() from exc
