from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from app.domains.audit.service import AuditLogService
from app.domains.order_adjustments.exceptions import (
    OrderingAdjustmentAlreadyConfirmedError, OrderingAdjustmentExistingDraftError,
    OrderingAdjustmentInvariantError, OrderingAdjustmentLineNotFoundError,
    OrderingAdjustmentNotFoundError, OrderingAdjustmentSnapshotLockedError,
    OrderingAdjustmentStaleError, OrderingAdjustmentStateError,
    OrderingAdjustmentVersionConflictError,
)
from app.domains.order_adjustments.models import OrderingAdjustmentLine, OrderingAdjustmentSheet
from app.domains.order_adjustments.repository import OrderingAdjustmentRepository
from app.domains.requirements.repository import RequirementRepository
from app.domains.requirements.exceptions import RequirementMenuNotFoundError
from app.domains.requirements.schemas import RequirementCriteria
from app.domains.requirements.service import RequirementService
from app.domains.snapshots.fingerprint import hash_payload, normalize, snapshot_fingerprint
from app.domains.snapshots.service import SnapshotService
from app.shared.domain.quantities import calculate_required_quantity, convert_quantity, quantize_quantity


def _source_plan(rows):
    plans=[]
    for row in rows:
        if row["recipe_detail_id"] is None or row["ingredient_id"] is None or row["recipe_quantity"] <= 0: continue
        raw=calculate_required_quantity(row["recipe_quantity"],row["diner_count"],row["loss_rate"])
        converted=convert_quantity(raw,row["recipe_unit"],row["base_unit"])
        convertible=converted.convertible and converted.quantity is not None
        quantity=converted.quantity if convertible else raw
        unit=row["base_unit"] if convertible else row["recipe_unit"]
        context={
            "source_menu_id":row["menu_id"],"menu_name_snapshot":row["menu_name"],
            "source_menu_day_id":row["menu_day_id"],"requirement_date":row["menu_date"],
            "source_meal_type_id":row["meal_type_id"],"meal_type_name_snapshot":row["meal_type_name"],
            "meal_type_sort_order_snapshot":row["meal_type_sort_order"],
            "source_menu_meal_type_column_id":row["menu_meal_type_column_id"],
            "menu_meal_type_column_sort_order_snapshot":row["menu_meal_type_column_sort_order"],
            "source_menu_dish_id":row["menu_dish_id"],"source_dish_id":row["dish_id"],
            "menu_dish_sort_order_snapshot":row["menu_dish_sort_order"],
            "dish_code_snapshot":row["dish_code"],"dish_name_snapshot":row["dish_name"],"diner_count_snapshot":row["diner_count"],
            "source_dish_ingredient_id":row["recipe_detail_id"],"source_ingredient_id":row["ingredient_id"],
            "dish_ingredient_sort_order_snapshot":row["dish_ingredient_sort_order"],
            "ingredient_code_snapshot":row["ingredient_code"],"ingredient_name_snapshot":row["ingredient_name"],
            "source_supplier_id":row["supplier_id"],"supplier_name_snapshot":row["supplier_name"],
            "quantity_per_person_snapshot":row["recipe_quantity"],"loss_rate_snapshot":row["loss_rate"],
            "recipe_unit_snapshot":row["recipe_unit"],"ingredient_base_unit_snapshot":row["base_unit"],
            "configured_purchase_unit_snapshot":row["purchase_unit"],"package_size_snapshot":row["package_size"],
            "minimum_order_quantity_snapshot":row["minimum_order_quantity"],"current_price_snapshot":row["current_price"],
            "system_quantity":quantize_quantity(quantity),"system_unit":unit,
        }
        context["source_line_key"]=f'{row["menu_dish_id"]}:{row["recipe_detail_id"]}'
        context["row_key"]=f'{row["ingredient_id"]}:{unit}'
        context["source_signature"]=hash_payload(context)
        context["_theoretical_quantity"]=quantity
        plans.append(context)
    return sorted(plans,key=lambda item:item["source_line_key"])


def _stale_reasons(saved,live):
    if live is None:return ["SOURCE_REMOVED"]
    mapping={
        "diner_count_snapshot":"DINER_COUNT_CHANGED","quantity_per_person_snapshot":"RECIPE_QUANTITY_CHANGED",
        "loss_rate_snapshot":"LOSS_RATE_CHANGED","source_supplier_id":"SUPPLIER_CHANGED",
        "recipe_unit_snapshot":"UNIT_CHANGED","ingredient_base_unit_snapshot":"UNIT_CHANGED",
        "system_unit":"UNIT_CHANGED","source_menu_day_id":"MENU_DISH_MOVED","requirement_date":"MENU_DISH_MOVED",
        "source_meal_type_id":"MENU_DISH_MOVED","source_dish_id":"DISH_CHANGED",
        "source_ingredient_id":"INGREDIENT_CHANGED","configured_purchase_unit_snapshot":"PURCHASING_DATA_CHANGED",
        "package_size_snapshot":"PURCHASING_DATA_CHANGED","minimum_order_quantity_snapshot":"PURCHASING_DATA_CHANGED",
        "current_price_snapshot":"PURCHASING_DATA_CHANGED","system_quantity":"SOURCE_QUANTITY_CHANGED",
    }
    reasons=[]
    for field,reason in mapping.items():
        left=getattr(saved,field);right=live[field]
        if isinstance(left,Decimal) or isinstance(right,Decimal):
            if Decimal(left or 0)!=Decimal(right or 0):reasons.append(reason)
        elif left!=right:reasons.append(reason)
    if saved.source_signature!=live["source_signature"] and not reasons: reasons.append("SOURCE_CHANGED")
    return list(dict.fromkeys(reasons))


def _source_fingerprint(criteria,plans):
    return hash_payload({"criteria":criteria.model_dump(exclude_none=True),"lines":[{"key":p["source_line_key"],"signature":p["source_signature"]} for p in plans]})


def _assert_theoretical_totals(plans,items):
    by_key={item.row_key:item for item in items};totals=defaultdict(Decimal)
    for plan in plans:
        item=by_key.get(plan["row_key"])
        if item is None:raise OrderingAdjustmentInvariantError()
        totals[item.id]+=plan["_theoretical_quantity"]
    if any(quantize_quantity(totals[item.id])!=quantize_quantity(item.requirement_quantity) for item in items):raise OrderingAdjustmentInvariantError()
    return by_key


class OrderingAdjustmentService:
    def __init__(self,session):
        self.session=session;self.repository=OrderingAdjustmentRepository(session);self.audit=AuditLogService(session)

    def create(self,criteria,actor_id,notes=None):
        try:
            normalized=normalize(criteria.model_dump(exclude_none=True));criteria_hash=snapshot_fingerprint(normalized)
            self.repository.lock_creation_key(criteria_hash)
            requirements=RequirementRepository(self.session)
            source=requirements.locked_source_rows(criteria)
            menus=requirements.menus(criteria.menu_ids)
            if len(menus)!=len(criteria.menu_ids):raise RequirementMenuNotFoundError()
            result=RequirementService(self.session).calculate_from_source(criteria,menus,source)
            plans=_source_plan(source);fingerprint=_source_fingerprint(criteria,plans)
            existing=self.repository.sheet_for_source(criteria_hash,fingerprint,{"draft","confirmed"})
            if existing and existing.status=="draft":raise OrderingAdjustmentExistingDraftError(existing.id)
            if existing:raise OrderingAdjustmentAlreadyConfirmedError(existing.id)
            header,items,_=SnapshotService(self.session).build(criteria,actor_id,result=result,allow_duplicate=True,snapshot_kind="ordering_adjustment")
            by_key=_assert_theoretical_totals(plans,items)
            sheet=OrderingAdjustmentSheet(baseline_snapshot_id=header.id,status="draft",source_fingerprint=fingerprint,criteria_fingerprint=criteria_hash,revision=header.revision,lock_version=1,notes=notes,created_by=actor_id,updated_by=actor_id)
            self.repository.add(sheet);self.session.flush()
            for plan in plans:
                values={key:value for key,value in plan.items() if key not in {"row_key","_theoretical_quantity"}}
                self.repository.add(OrderingAdjustmentLine(sheet_id=sheet.id,snapshot_item_id=by_key[plan["row_key"]].id,adjusted_quantity=None,created_by=actor_id,updated_by=actor_id,**values))
            self.audit.record(actor_id=actor_id,action="ordering_adjustment_create",entity_type="ordering_adjustment_sheet",entity_id=sheet.id,entity_label=f"Revision {sheet.revision}",after_data={"baseline_snapshot_id":header.id,"line_count":len(plans),"source_fingerprint":fingerprint})
            self.session.commit()
        except Exception:
            self.session.rollback();raise
        return self.detail(sheet.id)

    def _loaded(self,sheet_id,for_update=False):
        sheet=self.repository.sheet(sheet_id,for_update)
        if not sheet:raise OrderingAdjustmentNotFoundError()
        return sheet,self.repository.lines(sheet_id,for_update)

    def _live(self,sheet,lines,*,lock_source=False):
        snapshot=self.repository.snapshot(sheet.baseline_snapshot_id)
        criteria=RequirementCriteria.model_validate(snapshot.criteria)
        requirements=RequirementRepository(self.session)
        source=requirements.locked_source_rows(criteria) if lock_source else requirements.source_rows(criteria)
        plans=_source_plan(source);live={p["source_line_key"]:p for p in plans}
        line_state={line.id:_stale_reasons(line,live.get(line.source_line_key)) for line in lines}
        saved={line.source_line_key for line in lines};warnings=[]
        for key in sorted(set(live)-saved):warnings.append({"code":"NEW_SOURCE_LINE","source_line_key":key})
        live_fingerprint=_source_fingerprint(criteria,plans)
        if live_fingerprint!=sheet.source_fingerprint:warnings.append({"code":"SOURCE_FINGERPRINT_CHANGED"})
        return snapshot,line_state,warnings,plans

    def detail(self,sheet_id):
        sheet,lines=self._loaded(sheet_id);snapshot=self.repository.snapshot(sheet.baseline_snapshot_id)
        line_state={line.id:[] for line in lines};warnings=[]
        if sheet.status=="draft":snapshot,line_state,warnings,_=self._live(sheet,lines)
        data={column.name:getattr(sheet,column.name) for column in sheet.__table__.columns}
        data.update(criteria=snapshot.criteria,source_menus=snapshot.source_menus,stale=bool(warnings or any(line_state.values())),warnings=warnings)
        data["lines"]=[]
        for line in lines:
            value={column.name:getattr(line,column.name) for column in line.__table__.columns}
            value.update(effective_quantity=line.adjusted_quantity if line.adjusted_quantity is not None else line.system_quantity,modified=line.adjusted_quantity is not None,stale=bool(line_state[line.id]),stale_reasons=line_state[line.id])
            data["lines"].append(value)
        return data

    def update_lines(self,sheet_id,updates,lock_version,actor_id):
        try:
            sheet,lines=self._loaded(sheet_id,True)
            self._assert_mutable(sheet,lock_version)
            by_id={line.id:line for line in lines};before=[];after=[]
            for update in updates:
                line=by_id.get(update.id)
                if not line:raise OrderingAdjustmentLineNotFoundError()
                before.append({"id":line.id,"adjusted_quantity":line.adjusted_quantity})
                line.adjusted_quantity=None if update.adjusted_quantity is None else quantize_quantity(update.adjusted_quantity);line.updated_by=actor_id
                after.append({"id":line.id,"adjusted_quantity":line.adjusted_quantity})
            sheet.lock_version+=1;sheet.updated_by=actor_id
            self.audit.record(actor_id=actor_id,action="ordering_adjustment_lines_update",entity_type="ordering_adjustment_sheet",entity_id=sheet.id,entity_label=f"Revision {sheet.revision}",before_data={"lock_version":lock_version,"lines":before},after_data={"lock_version":sheet.lock_version,"lines":after})
            self.session.commit()
        except Exception:self.session.rollback();raise
        return self.detail(sheet_id)

    def confirm(self,sheet_id,lock_version,actor_id):
        try:
            sheet,lines=self._loaded(sheet_id,True);self._assert_mutable(sheet,lock_version)
            if self.repository.purchase(sheet.baseline_snapshot_id):raise OrderingAdjustmentSnapshotLockedError()
            _,states,warnings,plans=self._live(sheet,lines,lock_source=True)
            stale=[{"line_id":str(line_id),"reasons":reasons} for line_id,reasons in states.items() if reasons]+warnings
            if stale:raise OrderingAdjustmentStaleError(stale)
            items=self.repository.snapshot_items(sheet.baseline_snapshot_id,True);by_id={item.id:item for item in items}
            _assert_theoretical_totals(plans,items);finals=defaultdict(Decimal)
            for line in lines:
                item=by_id.get(line.snapshot_item_id)
                if not item:raise OrderingAdjustmentInvariantError()
                target=item.purchase_unit_snapshot or item.requirement_unit
                value=line.adjusted_quantity if line.adjusted_quantity is not None else line.system_quantity
                converted=convert_quantity(value,line.system_unit,target)
                if not converted.convertible or converted.quantity is None:raise OrderingAdjustmentInvariantError()
                finals[item.id]+=converted.quantity
            for item in items:item.adjusted_quantity=quantize_quantity(finals[item.id]);item.updated_by=actor_id
            sheet.status="confirmed";sheet.confirmed_at=datetime.now(UTC);sheet.confirmed_by=actor_id;sheet.updated_by=actor_id;sheet.lock_version+=1
            self.audit.record(actor_id=actor_id,action="ordering_adjustment_confirm",entity_type="ordering_adjustment_sheet",entity_id=sheet.id,entity_label=f"Revision {sheet.revision}",before_data={"status":"draft","lock_version":lock_version},after_data={"status":"confirmed","lock_version":sheet.lock_version,"baseline_snapshot_id":sheet.baseline_snapshot_id})
            self.session.commit()
        except Exception:self.session.rollback();raise
        return self.detail(sheet_id)

    def cancel(self,sheet_id,lock_version,actor_id):
        try:
            sheet,_=self._loaded(sheet_id,True);self._assert_mutable(sheet,lock_version)
            if self.repository.purchase(sheet.baseline_snapshot_id):raise OrderingAdjustmentSnapshotLockedError()
            sheet.status="cancelled";sheet.updated_by=actor_id;sheet.lock_version+=1
            self.audit.record(actor_id=actor_id,action="ordering_adjustment_cancel",entity_type="ordering_adjustment_sheet",entity_id=sheet.id,entity_label=f"Revision {sheet.revision}",before_data={"status":"draft","lock_version":lock_version},after_data={"status":"cancelled","lock_version":sheet.lock_version})
            self.session.commit()
        except Exception:self.session.rollback();raise
        return self.detail(sheet_id)

    def _assert_mutable(self,sheet,lock_version):
        if sheet.status!="draft":raise OrderingAdjustmentStateError()
        if sheet.lock_version!=lock_version:raise OrderingAdjustmentVersionConflictError()
        if self.repository.purchase(sheet.baseline_snapshot_id):raise OrderingAdjustmentSnapshotLockedError()

    def list(self,page,page_size,status=None,menu_id=None,start_date=None,end_date=None):
        rows,total=self.repository.listing(page,page_size,status,menu_id,start_date,end_date)
        values=[]
        for sheet,snapshot,created_by_name in rows:
            data={column.name:getattr(sheet,column.name) for column in sheet.__table__.columns}
            data.update(criteria=snapshot.criteria,source_menus=snapshot.source_menus,created_by_name=created_by_name,stale=None)
            values.append(data)
        return values,total
