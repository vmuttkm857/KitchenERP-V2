import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

StepType = Literal["wash","cut","chop","marinate","blanch","thaw","stir_fry","boil","braise","steam","bake","fry","pan_fry","add_ingredient","add_water","stir","flip","thicken","sauce","garnish","final_addition","portion","plating","quality_check","other"]
UsageCategory = Literal["main_ingredient","preprocessing","marinade","seasoning","sauce","final_addition","garnish"]

class ProfileCreate(BaseModel):
    max_batch_size:int=Field(gt=0,le=100000);notes:str|None=Field(default=None,max_length=5000)
class ProfileUpdate(BaseModel):
    max_batch_size:int|None=Field(default=None,gt=0,le=100000);notes:str|None=Field(default=None,max_length=5000)
class VersionCreate(BaseModel):
    serving_count:int=Field(gt=0,le=100000);name:str|None=Field(default=None,max_length=150);is_official:bool=False;notes:str|None=Field(default=None,max_length=5000)
class VersionCopy(BaseModel):
    serving_count:int=Field(gt=0,le=100000);name:str|None=Field(default=None,max_length=150);is_official:bool=False
class VersionUpdate(BaseModel):
    serving_count:int|None=Field(default=None,gt=0,le=100000);name:str|None=Field(default=None,max_length=150);is_official:bool|None=None;notes:str|None=Field(default=None,max_length=5000)
class IngredientUpdate(BaseModel):
    quantity:Decimal|None=Field(default=None,ge=0,max_digits=24,decimal_places=10);unit:str|None=Field(default=None,min_length=1,max_length=30);usage_category:UsageCategory|None=None;quantity_note:str|None=Field(default=None,max_length=500);notes:str|None=Field(default=None,max_length=1000)
class StepCreate(BaseModel):
    step_order:int=Field(ge=1);step_type:StepType;title:str|None=Field(default=None,max_length=150);instruction:str|None=Field(default=None,max_length=10000);equipment:str|None=Field(default=None,max_length=150);duration_seconds:int|None=Field(default=None,ge=0);temperature_celsius:Decimal|None=Field(default=None,ge=-100,le=500);batch_size:int|None=Field(default=None,gt=0);servings_per_tray:int|None=Field(default=None,gt=0);trays_per_batch:int|None=Field(default=None,gt=0);quantity_note:str|None=Field(default=None,max_length=500);notes:str|None=Field(default=None,max_length=1000)
class StepUpdate(BaseModel):
    step_order:int|None=Field(default=None,ge=1);step_type:StepType|None=None;title:str|None=Field(default=None,max_length=150);instruction:str|None=Field(default=None,max_length=10000);equipment:str|None=Field(default=None,max_length=150);duration_seconds:int|None=Field(default=None,ge=0);temperature_celsius:Decimal|None=Field(default=None,ge=-100,le=500);batch_size:int|None=Field(default=None,gt=0);servings_per_tray:int|None=Field(default=None,gt=0);trays_per_batch:int|None=Field(default=None,gt=0);quantity_note:str|None=Field(default=None,max_length=500);notes:str|None=Field(default=None,max_length=1000)
class StepReorder(BaseModel): ordered_ids:list[uuid.UUID]=Field(min_length=1,max_length=200)

class IngredientPublic(BaseModel):
    id:uuid.UUID;dish_ingredient_id:uuid.UUID|None;ingredient_id:uuid.UUID;ingredient_code:str;ingredient_name:str;quantity:Decimal;unit:str;usage_category:str;sort_order:int;quantity_note:str|None;notes:str|None
class StepPublic(BaseModel):
    id:uuid.UUID;step_order:int;step_type:str;title:str|None;instruction:str|None;equipment:str|None;duration_seconds:int|None;temperature_celsius:Decimal|None;batch_size:int|None;servings_per_tray:int|None;trays_per_batch:int|None;quantity_note:str|None;notes:str|None
class VersionPublic(BaseModel):
    id:uuid.UUID;serving_count:int;name:str|None;is_official:bool;notes:str|None;created_at:datetime;updated_at:datetime;ingredients:list[IngredientPublic];steps:list[StepPublic]
class ProfilePublic(BaseModel):
    id:uuid.UUID;dish_id:uuid.UUID;dish_code:str;dish_name:str;max_batch_size:int;notes:str|None;has_image:bool;image_mime_type:str|None;image_size_bytes:int|None;created_at:datetime;updated_at:datetime;versions:list[VersionPublic]
class PlannedIngredient(BaseModel): ingredient_id:uuid.UUID;ingredient_code:str;ingredient_name:str;quantity:Decimal;unit:str;usage_category:str;quantity_note:str|None;notes:str|None
class PlannedBatch(BaseModel): batch_number:int;serving_count:int;official:bool;version_id:uuid.UUID|None;version_name:str|None;version_notes:str|None;source_serving_count:int|None;ingredients:list[PlannedIngredient];steps:list[StepPublic]
class DishPlan(BaseModel): dish_id:uuid.UUID;dish_code:str;dish_name:str;diner_count:int;sort_order:int;notes:str|None;profile_notes:str|None;profile_missing:bool;max_batch_size:int|None;has_image:bool;batch_count:int;batches:list[PlannedBatch]
class MealPlan(BaseModel): meal_type_id:uuid.UUID;meal_type_name:str;meal_order:int;dishes:list[DishPlan]
class DayPlan(BaseModel): menu_date:date;meals:list[MealPlan]
class MenuProductionPlan(BaseModel): menu_id:uuid.UUID;menu_name:str;days:list[DayPlan]
