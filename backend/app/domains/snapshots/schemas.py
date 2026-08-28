import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any
from pydantic import BaseModel,ConfigDict,Field,field_serializer
from app.domains.requirements.schemas import RequirementCriteria
from app.shared.schemas import PaginationMeta

class SnapshotCreate(BaseModel): criteria:RequirementCriteria
class SnapshotItemUpdate(BaseModel): adjusted_quantity:Decimal=Field(ge=0)

class SnapshotItemPublic(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:uuid.UUID; row_key:str; ingredient_id:uuid.UUID|None; ingredient_code_snapshot:str; ingredient_name_snapshot:str
    supplier_id:uuid.UUID|None; supplier_code_snapshot:str|None; supplier_name_snapshot:str|None
    requirement_quantity:Decimal; requirement_unit:str; suggested_purchase_quantity:Decimal|None; adjusted_quantity:Decimal|None
    suggested_purchase_unit_snapshot:str|None; purchase_unit_snapshot:str|None; package_size_snapshot:Decimal; minimum_order_quantity_snapshot:Decimal
    unit_price_snapshot:Decimal|None; estimated_cost_snapshot:Decimal|None; needs_review:bool; total_diner_count:int; source_count:int
    anomaly_snapshot:list[dict[str,Any]]; source_summary:list[dict[str,Any]]; created_at:datetime; updated_at:datetime; updated_by:uuid.UUID
    @field_serializer("requirement_quantity","suggested_purchase_quantity","adjusted_quantity","package_size_snapshot","minimum_order_quantity_snapshot","unit_price_snapshot","estimated_cost_snapshot")
    def decimal_string(self,value): return None if value is None else format(value,"f")

class SnapshotHeaderPublic(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:uuid.UUID; fingerprint:str; criteria:dict[str,Any]; source_menus:list[dict[str,Any]]; anomaly_snapshot:list[dict[str,Any]]; anomaly_summary:dict[str,Any]
    known_estimated_cost:Decimal; total_estimated_cost:Decimal|None; created_at:datetime; created_by:uuid.UUID; created_by_name:str|None=None
    @field_serializer("known_estimated_cost","total_estimated_cost")
    def decimal_string(self,value): return None if value is None else format(value,"f")

class SnapshotDetail(SnapshotHeaderPublic): items:list[SnapshotItemPublic]
class SnapshotList(BaseModel): items:list[SnapshotHeaderPublic]; pagination:PaginationMeta
