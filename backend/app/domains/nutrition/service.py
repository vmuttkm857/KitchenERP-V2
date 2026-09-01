from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import delete, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.audit.service import AuditLogService, audit_snapshot
from app.domains.auth.service import AuthService
from app.domains.ingredients.models import Ingredient
from app.domains.nutrition.exceptions import InvalidNutritionSourceError, NutritionFoodInUseError, NutritionFoodNotFoundError, NutritionImportError
from app.domains.nutrition.importer import CANONICAL, ParsedWorkbook, parse_tfda_xlsx
from app.domains.nutrition.models import NutritionFood, NutritionFoodValue, NutritionImportBatch, NutritionNutrient
from app.domains.nutrition.repository import NutritionRepository
from app.domains.nutrition.schemas import ManualFoodCreate, ManualFoodUpdate

MANUAL_DEFINITIONS = {
    "corrected_energy": ("修正熱量", "kcal"), "energy": ("熱量", "kcal"), "protein": ("粗蛋白", "g"),
    "fat": ("粗脂肪", "g"), "carbohydrate": ("總碳水化合物", "g"), "dietary_fiber": ("膳食纖維", "g"),
    "sodium": ("鈉", "mg"), "potassium": ("鉀", "mg"), "calcium": ("鈣", "mg"),
}


class NutritionService:
    def __init__(self, session: Session): self.session = session; self.repository = NutritionRepository(session); self.audit = AuditLogService(session)
    def get(self, food_id: uuid.UUID):
        detail = self.repository.detail(food_id)
        if not detail: raise NutritionFoodNotFoundError()
        food, values = detail
        return {**{column.name: getattr(food, column.name) for column in NutritionFood.__table__.columns if column.name not in {"source_hash", "last_import_batch_id", "created_by", "updated_by", "created_at", "updated_at"}}, "values": values}
    def list(self, **kwargs): return self.repository.list_foods(**kwargs)
    def categories(self, source: str): return self.repository.categories(source)
    def imports(self, page: int, page_size: int): return self.repository.imports(page, page_size)
    def _parse(self, payload: bytes, filename: str) -> ParsedWorkbook:
        if Path(filename).suffix.lower() != ".xlsx": raise NutritionImportError("只允許 .xlsx 檔案")
        return parse_tfda_xlsx(payload)
    def preview(self, payload: bytes, filename: str):
        return self._summary(self._parse(payload, filename))
    def _summary(self, parsed: ParsedWorkbook):
        existing = self.repository.tfda_by_code(); incoming = {food.external_code: food for food in parsed.foods}
        inserted = sum(code not in existing for code in incoming)
        updated = sum(code in existing and (existing[code].source_hash != food.source_hash or not existing[code].active_in_latest_import) for code, food in incoming.items())
        unchanged = len(incoming) - inserted - updated; missing = sum(code not in incoming for code in existing)
        return {"header_row": parsed.header_row, "total_rows": len(parsed.foods), "inserted_count": inserted, "updated_count": updated, "unchanged_count": unchanged, "missing_count": missing, "error_count": len(parsed.errors), "errors": parsed.errors[:100]}
    def _ensure_nutrients(self, parsed: ParsedWorkbook | None = None):
        existing = self.repository.nutrients_by_code(); definitions = []
        if parsed: definitions.extend(parsed.nutrients)
        for order, (code, (name, unit)) in enumerate(MANUAL_DEFINITIONS.items(), 1):
            if code not in {item.code for item in definitions}: definitions.append(type("Definition", (), {"code": code, "name": name, "unit": unit, "original_source_name": next((h for h, mapped in CANONICAL.items() if mapped == code), None), "sort_order": order})())
        for definition in definitions:
            nutrient = existing.get(definition.code)
            if nutrient is None:
                nutrient = NutritionNutrient(code=definition.code, name=definition.name, unit=definition.unit, sort_order=definition.sort_order, original_source_name=definition.original_source_name)
                self.session.add(nutrient); existing[definition.code] = nutrient
            elif definition.original_source_name and not nutrient.original_source_name: nutrient.original_source_name = definition.original_source_name
        self.session.flush(); return existing
    def confirm(self, payload: bytes, filename: str, version_label: str | None, actor_id: uuid.UUID):
        parsed = self._parse(payload, filename); summary = self._summary(parsed); safe_filename = Path(filename).name[:255]
        try:
            batch = NutritionImportBatch(id=uuid.uuid4(), source="tfda", version_label=version_label.strip() if version_label else None, original_filename=safe_filename, source_hash=parsed.source_hash, header_row=parsed.header_row, imported_by=actor_id, status="processing", notes=None, **{key: summary[key] for key in ("total_rows", "inserted_count", "updated_count", "unchanged_count", "missing_count", "error_count")})
            self.session.add(batch); self.session.flush(); nutrients = self._ensure_nutrients(parsed); existing = self.repository.tfda_by_code(); incoming_codes = {food.external_code for food in parsed.foods}; changed_ids = []
            for parsed_food in parsed.foods:
                food = existing.get(parsed_food.external_code)
                if food is None:
                    food = NutritionFood(id=uuid.uuid4(), source="tfda", external_code=parsed_food.external_code, name=parsed_food.name, category=parsed_food.category, description=parsed_food.description, aliases=parsed_food.aliases, waste_rate=parsed_food.waste_rate, is_active=True, active_in_latest_import=True, source_hash=parsed_food.source_hash, last_import_batch_id=batch.id, created_by=actor_id, updated_by=actor_id)
                    self.session.add(food); existing[parsed_food.external_code] = food; changed_ids.append(food.id)
                elif food.source_hash != parsed_food.source_hash or not food.active_in_latest_import:
                    food.name=parsed_food.name; food.category=parsed_food.category; food.description=parsed_food.description; food.aliases=parsed_food.aliases; food.waste_rate=parsed_food.waste_rate; food.active_in_latest_import=True; food.source_hash=parsed_food.source_hash; food.last_import_batch_id=batch.id; food.updated_by=actor_id; changed_ids.append(food.id)
                else: food.last_import_batch_id=batch.id
            for code, food in existing.items():
                if code not in incoming_codes: food.active_in_latest_import=False; food.updated_by=actor_id
            self.session.flush()
            if changed_ids:
                self.session.execute(delete(NutritionFoodValue).where(NutritionFoodValue.food_id.in_(changed_ids)))
                rows=[]
                parsed_by_code={food.external_code:food for food in parsed.foods}
                for code, food in existing.items():
                    if food.id not in changed_ids: continue
                    for nutrient_code, value in parsed_by_code[code].values.items(): rows.append({"food_id":food.id,"nutrient_id":nutrients[nutrient_code].id,"value":value})
                for start in range(0,len(rows),5000): self.session.execute(insert(NutritionFoodValue),rows[start:start+5000])
            batch.status="completed_with_warnings" if parsed.errors else "completed"
            self.audit.record(actor_id=actor_id, action="nutrition_import_confirm", entity_type="nutrition_import_batch", entity_id=batch.id, entity_label=safe_filename, metadata={"batch_id":batch.id,"filename":safe_filename,**{key:summary[key] for key in ("total_rows","inserted_count","updated_count","unchanged_count","missing_count","error_count")}})
            self.session.commit(); self.session.refresh(batch); return batch
        except Exception:
            self.session.rollback(); raise
    def _manual_values(self, food_id: uuid.UUID, data, nutrients):
        self.session.execute(delete(NutritionFoodValue).where(NutritionFoodValue.food_id == food_id))
        rows=[{"food_id":food_id,"nutrient_id":nutrients[code].id,"value":value} for code,value in data.model_dump().items() if value is not None]
        if rows: self.session.execute(insert(NutritionFoodValue),rows)
    def create_manual(self, data: ManualFoodCreate, actor_id: uuid.UUID):
        try:
            nutrients=self._ensure_nutrients(); food=NutritionFood(id=uuid.uuid4(),source="manual",name=data.name.strip(),brand=data.brand,source_note=data.source_note,notes=data.notes,is_active=True,active_in_latest_import=True,created_by=actor_id,updated_by=actor_id)
            self.session.add(food);self.session.flush();self._manual_values(food.id,data.nutrients,nutrients)
            self.audit.record(actor_id=actor_id,action="nutrition_manual_create",entity_type="nutrition_food",entity_id=food.id,entity_label=food.name,after_data=audit_snapshot(food,"source","name","brand","source_note","notes","is_active"));self.session.commit();return self.get(food.id)
        except Exception:self.session.rollback();raise
    def update_manual(self, food_id: uuid.UUID, data: ManualFoodUpdate, actor_id: uuid.UUID):
        food=self.repository.food(food_id)
        if not food: raise NutritionFoodNotFoundError()
        if food.source!="manual": raise InvalidNutritionSourceError("官方資料只讀")
        before=audit_snapshot(food,"name","brand","source_note","notes","is_active");changes=data.model_dump(exclude_unset=True);values=changes.pop("nutrients",None)
        for key,value in changes.items():setattr(food,key,value.strip() if key=="name" and value else value)
        food.updated_by=actor_id
        try:
            if values is not None:self._manual_values(food.id,data.nutrients,self._ensure_nutrients())
            self.audit.record(actor_id=actor_id,action="nutrition_manual_update",entity_type="nutrition_food",entity_id=food.id,entity_label=food.name,before_data=before,after_data=audit_snapshot(food,"name","brand","source_note","notes","is_active"));self.session.commit();return self.get(food.id)
        except Exception:self.session.rollback();raise
    def set_manual_active(self, food_id: uuid.UUID, active: bool, actor_id: uuid.UUID):
        food=self.repository.food(food_id)
        if not food: raise NutritionFoodNotFoundError()
        if food.source!="manual": raise InvalidNutritionSourceError("官方資料只讀")
        before={"is_active":food.is_active};food.is_active=active;food.updated_by=actor_id;self.audit.record(actor_id=actor_id,action="nutrition_manual_reactivate" if active else "nutrition_manual_deactivate",entity_type="nutrition_food",entity_id=food.id,entity_label=food.name,before_data=before,after_data={"is_active":active});self.session.commit();return self.get(food.id)
    def hard_delete_manual(self, food_id: uuid.UUID, actor_id: uuid.UUID, password: str):
        AuthService(self.session).verify_current_password(actor_id,password);food=self.repository.food(food_id)
        if not food:raise NutritionFoodNotFoundError()
        if food.source!="manual":raise InvalidNutritionSourceError("官方資料不可永久刪除")
        if self.repository.ingredient_uses(food_id):raise NutritionFoodInUseError()
        before=audit_snapshot(food,"source","name","brand","is_active");self.session.delete(food);self.audit.record(actor_id=actor_id,action="nutrition_hard_delete",entity_type="nutrition_food",entity_id=food.id,entity_label=food.name,before_data=before)
        try:self.session.commit()
        except IntegrityError as exc:self.session.rollback();raise NutritionFoodInUseError() from exc
    def set_ingredient_mapping(self, ingredient_id: uuid.UUID, food_id: uuid.UUID | None, actor_id: uuid.UUID):
        ingredient=self.session.get(Ingredient,ingredient_id)
        if not ingredient: from app.domains.ingredients.exceptions import IngredientNotFoundError; raise IngredientNotFoundError()
        if food_id is not None:
            food=self.repository.food(food_id)
            if not food or not food.is_active:raise NutritionFoodNotFoundError()
        old=ingredient.nutrition_food_id;ingredient.nutrition_food_id=food_id;ingredient.updated_by=actor_id
        self.audit.record(actor_id=actor_id,action="ingredient_nutrition_mapping_change",entity_type="ingredient",entity_id=ingredient.id,entity_label=ingredient.name,before_data={"nutrition_food_id":old},after_data={"nutrition_food_id":food_id});self.session.commit()
