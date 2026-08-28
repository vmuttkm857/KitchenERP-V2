import uuid
from datetime import date
from decimal import Decimal
from typing import Any,Literal
from pydantic import BaseModel,Field,field_serializer,model_validator

class KitchenCriteria(BaseModel):
    menu_id:uuid.UUID
    selected_dates:list[date]|None=Field(default=None,max_length=366)
    start_date:date|None=None;end_date:date|None=None
    meal_type_ids:list[uuid.UUID]|None=Field(default=None,max_length=50)
    display_mode:Literal["auto","raw"]="auto"
    @model_validator(mode="after")
    def valid(self):
        if self.selected_dates is not None and (self.start_date is not None or self.end_date is not None):raise ValueError("Use selected dates or a date range")
        if (self.start_date is None)!=(self.end_date is None):raise ValueError("Both range dates are required")
        if self.start_date and self.end_date and self.end_date<self.start_date:raise ValueError("Invalid date range")
        if self.selected_dates is not None:self.selected_dates=sorted(set(self.selected_dates))
        if self.meal_type_ids is not None:self.meal_type_ids=list(dict.fromkeys(self.meal_type_ids))
        return self
class KitchenAnomaly(BaseModel):code:str;severity:Literal["warning","error"];message:str;related_entity_id:uuid.UUID|None;related_entity_name:str|None;context:dict[str,Any]
class PreparationIngredient(BaseModel):
    ingredient_id:uuid.UUID|None;ingredient_code:str|None;ingredient_name:str|None;supplier_id:uuid.UUID|None;supplier_name:str|None;quantity_per_person:Decimal|None;recipe_unit:str|None;loss_rate:Decimal|None;required_quantity:Decimal|None;required_unit:str|None;base_quantity:Decimal|None;base_unit:str|None;display_quantity:Decimal|None;display_unit:str|None;notes:str|None;ingredient_notes:str|None;sort_order:int|None;anomalies:list[KitchenAnomaly]
    @field_serializer("quantity_per_person","loss_rate","required_quantity","base_quantity","display_quantity")
    def decimal_string(self,value):return None if value is None else format(value,"f")
class PreparationDish(BaseModel):dish_id:uuid.UUID;dish_code:str;dish_name:str;diner_count:int;notes:str|None;sort_order:int;recipe_ready:bool;ingredients:list[PreparationIngredient];anomalies:list[KitchenAnomaly]
class PreparationMeal(BaseModel):meal_type_id:uuid.UUID;meal_type_name:str;sort_order:int;dishes:list[PreparationDish];anomalies:list[KitchenAnomaly]
class PreparationDay(BaseModel):menu_date:date;meals:list[PreparationMeal];anomalies:list[KitchenAnomaly]
class IngredientSummary(BaseModel):
    row_key:str;ingredient_id:uuid.UUID;ingredient_code:str;ingredient_name:str;supplier_id:uuid.UUID|None;supplier_name:str|None;required_quantity:Decimal;required_unit:str;display_quantity:Decimal;display_unit:str;source_count:int;anomalies:list[KitchenAnomaly]
    @field_serializer("required_quantity","display_quantity")
    def decimal_string(self,value):return format(value,"f")
class SupplierSummary(BaseModel):supplier_id:uuid.UUID|None;supplier_name:str;ingredients:list[IngredientSummary]
class KitchenResult(BaseModel):criteria:KitchenCriteria;menu:dict[str,Any];days:list[PreparationDay];ingredient_summary:list[IngredientSummary];supplier_summary:list[SupplierSummary];anomalies:list[KitchenAnomaly];anomaly_summary:dict[str,int]
