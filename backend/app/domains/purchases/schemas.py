import uuid
from datetime import date,datetime
from decimal import Decimal
from typing import Any,Literal
from pydantic import BaseModel,ConfigDict,Field,field_serializer
from app.shared.schemas import PaginationMeta

class PurchaseCreate(BaseModel):snapshot_id:uuid.UUID;notes:str|None=Field(default=None,max_length=2000)
class PurchaseItemPublic(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:uuid.UUID;source_snapshot_item_id:uuid.UUID;ingredient_id:uuid.UUID|None;ingredient_code_snapshot:str;ingredient_name_snapshot:str;supplier_id:uuid.UUID;supplier_code_snapshot:str|None;supplier_name_snapshot:str
    requirement_quantity_snapshot:Decimal;requirement_unit_snapshot:str;suggested_quantity_snapshot:Decimal|None;adjusted_quantity_snapshot:Decimal;final_purchase_quantity:Decimal;purchase_unit_snapshot:str
    package_size_snapshot:Decimal;minimum_order_quantity_snapshot:Decimal;unit_price_snapshot:Decimal|None;purchase_cost_snapshot:Decimal|None;anomaly_snapshot:list[dict[str,Any]];source_summary_snapshot:list[dict[str,Any]]
    @field_serializer("requirement_quantity_snapshot","suggested_quantity_snapshot","adjusted_quantity_snapshot","final_purchase_quantity","package_size_snapshot","minimum_order_quantity_snapshot","unit_price_snapshot","purchase_cost_snapshot")
    def decimals(self,value):return None if value is None else format(value,"f")
class SupplierOrderPublic(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:uuid.UUID;supplier_id:uuid.UUID;supplier_code_snapshot:str|None;supplier_name_snapshot:str;known_total_cost:Decimal;total_cost:Decimal|None;items:list[PurchaseItemPublic]=[]
    @field_serializer("known_total_cost","total_cost")
    def decimals(self,value):return None if value is None else format(value,"f")
class PurchasePublic(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:uuid.UUID;purchase_number:str;source_snapshot_id:uuid.UUID;source_snapshot_revision:int;source_summary_snapshot:list[dict[str,Any]];status:Literal["draft","confirmed","cancelled"]
    known_total_cost:Decimal;total_cost:Decimal|None;anomaly_snapshot:list[dict[str,Any]];notes:str|None;created_at:datetime;updated_at:datetime;created_by:uuid.UUID;updated_by:uuid.UUID;created_by_name:str|None=None;confirmed_at:datetime|None;cancelled_at:datetime|None
    supplier_summary:list[dict[str,Any]]=[]
    orders:list[SupplierOrderPublic]=[]
    @field_serializer("known_total_cost","total_cost")
    def decimals(self,value):return None if value is None else format(value,"f")
class PurchaseList(BaseModel):items:list[PurchasePublic];pagination:PaginationMeta
