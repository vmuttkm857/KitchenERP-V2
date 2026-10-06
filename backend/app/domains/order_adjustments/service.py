from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from app.domains.audit.service import AuditLogService
from app.domains.order_adjustments.aggregation import aggregate_effective_quantities
from app.domains.order_adjustments.exceptions import (
    OrderingAdjustmentAlreadyConfirmedError, OrderingAdjustmentExistingDraftError,
    OrderingAdjustmentInvariantError, OrderingAdjustmentLineNotFoundError,
    OrderingAdjustmentDeleteForbiddenError, OrderingAdjustmentNotFoundError, OrderingAdjustmentSnapshotLockedError,
    OrderingAdjustmentReuseError,
    OrderingAdjustmentStaleError, OrderingAdjustmentStateError,
    OrderingAdjustmentVersionConflictError,
)
from app.domains.order_adjustments.models import OrderingAdjustmentLine, OrderingAdjustmentSheet
from app.domains.order_adjustments.repository import OrderingAdjustmentRepository
from app.domains.order_adjustments.reuse import build_reuse_preview
from app.domains.requirements.repository import RequirementRepository
from app.domains.requirements.exceptions import RequirementMenuNotFoundError
from app.domains.requirements.exceptions import RequirementAdjustmentError
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


def _actionable_reuse_review(item):
    return item["status"]=="reference_only" and "CURRENT_ALREADY_ADJUSTED" not in item["reason_codes"]


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
            # An adjustment baseline is always theoretical; an incoming calculation
            # context must never recursively apply another adjustment.
            criteria=criteria.model_copy(update={"ordering_adjustment_sheet_ids":None})
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

    def requirement_context(self,sheet_ids,calculation_source,criteria):
        sheets=self.repository.sheets(sheet_ids)
        found={sheet.id for sheet in sheets}
        missing=[str(sheet_id) for sheet_id in sheet_ids if sheet_id not in found]
        if missing:raise RequirementAdjustmentError("ADJUSTMENT_NOT_FOUND",status_code=404,sheet_ids=missing)
        invalid=[{"sheet_id":str(sheet.id),"status":sheet.status} for sheet in sheets if sheet.status not in {"draft","confirmed"}]
        if invalid:raise RequirementAdjustmentError("ADJUSTMENT_STATUS_INVALID",sheets=invalid)
        lines=self.repository.lines_for_sheets(sheet_ids);by_sheet=defaultdict(list)
        for line in lines:by_sheet[line.sheet_id].append(line)
        confirmed_sheet_ids={sheet.id for sheet in sheets if sheet.status=="confirmed"}
        confirmed_item_ids={line.snapshot_item_id for line in lines if line.sheet_id in confirmed_sheet_ids}
        snapshot_items={item.id:item for item in self.repository.snapshot_items_by_ids(confirmed_item_ids)} if confirmed_item_ids else {}
        current_keys={f'{row["menu_dish_id"]}:{row["recipe_detail_id"]}' for row in calculation_source if row["recipe_detail_id"] is not None}
        overrides={};matched_sheets=set();frozen=[];frozen_keys=set()
        for sheet in sheets:
            sheet_lines=by_sheet[sheet.id]
            if sheet.status=="draft":
                _,states,warnings,_=self._live(sheet,sheet_lines)
                stale=[{"line_id":str(line_id),"reasons":reasons} for line_id,reasons in states.items() if reasons]+warnings
                if stale:raise RequirementAdjustmentError("ADJUSTMENT_STALE",sheet_id=str(sheet.id),reasons=stale)
            for line in sheet_lines:
                date_selected=(line.requirement_date in criteria.selected_dates) if criteria.selected_dates is not None else (
                    criteria.start_date<=line.requirement_date<=criteria.end_date if criteria.start_date is not None else True
                )
                selected=line.source_menu_id in criteria.menu_ids and date_selected
                if not selected or (sheet.status=="draft" and line.source_line_key not in current_keys):continue
                matched_sheets.add(sheet.id)
                if line.source_line_key in overrides:
                    raise RequirementAdjustmentError("ADJUSTMENT_DUPLICATE_OVERRIDE",source_line_key=line.source_line_key,sheet_ids=[str(overrides[line.source_line_key]["sheet_id"]),str(sheet.id)])
                overrides[line.source_line_key]={
                    "quantity":line.adjusted_quantity if line.adjusted_quantity is not None else line.system_quantity,
                    "unit":line.system_unit,"sheet_id":sheet.id,
                }
                if sheet.status=="confirmed":
                    frozen_keys.add(line.source_line_key);frozen.append(self._frozen_source_row(line,snapshot_items[line.snapshot_item_id]))
        unmatched=[str(sheet.id) for sheet in sheets if sheet.id not in matched_sheets]
        if unmatched:raise RequirementAdjustmentError("ADJUSTMENT_NO_SOURCE_OVERLAP",sheet_ids=unmatched)
        source=[row for row in calculation_source if f'{row["menu_dish_id"]}:{row["recipe_detail_id"]}' not in frozen_keys]
        source.extend(frozen)
        source.sort(key=lambda row:(str(row["menu_id"]),row["menu_date"],row["meal_type_sort_order"],row["menu_dish_sort_order"],row["dish_ingredient_sort_order"],str(row["recipe_detail_id"])))
        return source,overrides

    @staticmethod
    def _frozen_source_row(line,snapshot_item):
        return {
            "menu_id":line.source_menu_id,"menu_name":line.menu_name_snapshot,"menu_is_active":True,
            "menu_day_id":line.source_menu_day_id,"menu_date":line.requirement_date,
            "meal_type_id":line.source_meal_type_id,"meal_type_name":line.meal_type_name_snapshot,
            "meal_type_sort_order":line.meal_type_sort_order_snapshot,"meal_type_is_active":True,
            "menu_dish_id":line.source_menu_dish_id,"menu_meal_type_column_id":line.source_menu_meal_type_column_id,
            "menu_meal_type_column_sort_order":line.menu_meal_type_column_sort_order_snapshot,
            "diner_count":line.diner_count_snapshot,"menu_dish_sort_order":line.menu_dish_sort_order_snapshot,
            "dish_id":line.source_dish_id,"dish_code":line.dish_code_snapshot,"dish_name":line.dish_name_snapshot,"dish_is_active":True,
            "recipe_detail_id":line.source_dish_ingredient_id,"recipe_quantity":line.quantity_per_person_snapshot,
            "recipe_unit":line.recipe_unit_snapshot,"loss_rate":line.loss_rate_snapshot,"dish_ingredient_sort_order":line.dish_ingredient_sort_order_snapshot,
            "ingredient_id":line.source_ingredient_id,"ingredient_code":line.ingredient_code_snapshot,"ingredient_name":line.ingredient_name_snapshot,
            "base_unit":line.ingredient_base_unit_snapshot,"current_price":line.current_price_snapshot,
            "supplier_id":line.source_supplier_id,"supplier_code":snapshot_item.supplier_code_snapshot,"supplier_name":line.supplier_name_snapshot,
            "purchase_unit":line.configured_purchase_unit_snapshot,"package_size":line.package_size_snapshot,
            "minimum_order_quantity":line.minimum_order_quantity_snapshot,"ingredient_is_active":True,
            "supplier_is_active":True if line.source_supplier_id is not None else None,
        }

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
                before.append({"id":line.id,"adjusted_quantity":line.adjusted_quantity,"review_required":line.review_required})
                line.adjusted_quantity=None if update.adjusted_quantity is None else quantize_quantity(update.adjusted_quantity)
                line.review_required=False;line.updated_by=actor_id
                after.append({"id":line.id,"adjusted_quantity":line.adjusted_quantity,"review_required":line.review_required})
            sheet.lock_version+=1;sheet.updated_by=actor_id
            self.audit.record(actor_id=actor_id,action="ordering_adjustment_lines_update",entity_type="ordering_adjustment_sheet",entity_id=sheet.id,entity_label=f"Revision {sheet.revision}",before_data={"lock_version":lock_version,"lines":before},after_data={"lock_version":sheet.lock_version,"lines":after})
            self.session.commit()
        except Exception:self.session.rollback();raise
        return self.detail(sheet_id)

    def _reuse_loaded(self,current_sheet,previous_sheet,current_lines,previous_lines,menu_pairs,*,lock_source=False):
        self._assert_mutable(current_sheet,current_sheet.lock_version)
        current_snapshot=self.repository.snapshot(current_sheet.baseline_snapshot_id)
        previous_snapshot=self.repository.snapshot(previous_sheet.baseline_snapshot_id)
        current_menu_ids={str(menu["menu_id"]) for menu in current_snapshot.source_menus}
        previous_menu_ids={str(menu["menu_id"]) for menu in previous_snapshot.source_menus}
        paired_current={str(pair.current_menu_id) for pair in menu_pairs}
        paired_previous={str(pair.previous_menu_id) for pair in menu_pairs}
        if paired_current!=current_menu_ids or not paired_previous.issubset(previous_menu_ids):
            raise OrderingAdjustmentReuseError("INVALID_MENU_PAIRS")
        _,states,warnings,_=self._live(current_sheet,current_lines,lock_source=lock_source)
        stale=[{"line_id":str(line_id),"reasons":reasons} for line_id,reasons in states.items() if reasons]+warnings
        if stale:raise OrderingAdjustmentStaleError(stale)
        if previous_sheet.status=="cancelled":raise OrderingAdjustmentReuseError("PREVIOUS_STATUS_INVALID",status=previous_sheet.status)
        if previous_sheet.status=="draft":
            _,previous_states,previous_warnings,_=self._live(previous_sheet,previous_lines,lock_source=lock_source)
            previous_stale=[{"line_id":str(line_id),"reasons":reasons} for line_id,reasons in previous_states.items() if reasons]+previous_warnings
            if previous_stale:raise OrderingAdjustmentReuseError("PREVIOUS_ADJUSTMENT_STALE",reasons=previous_stale)
        values=build_reuse_preview(previous_lines,current_lines,previous_snapshot.source_menus,current_snapshot.source_menus,menu_pairs)
        summary={status:sum(item["status"]==status for item in values) for status in ("safe_to_reuse","reference_only","no_match","ambiguous")}
        summary["no_reusable_adjustment"]=sum("NO_REUSABLE_ADJUSTMENT" in item["reason_codes"] for item in values)
        summary["no_match"]-=summary["no_reusable_adjustment"]
        return {"current_sheet_id":current_sheet.id,"previous_sheet_id":previous_sheet.id,"current_lock_version":current_sheet.lock_version,"previous_lock_version":previous_sheet.lock_version,"summary":summary,"lines":values}

    def reuse_preview(self,sheet_id,data):
        if sheet_id==data.previous_sheet_id:raise OrderingAdjustmentReuseError("SAME_SHEET_NOT_ALLOWED")
        sheets=self.repository.sheets([sheet_id,data.previous_sheet_id])
        by_id={sheet.id:sheet for sheet in sheets}
        current=by_id.get(sheet_id);previous=by_id.get(data.previous_sheet_id)
        if not current or not previous:raise OrderingAdjustmentNotFoundError()
        if current.lock_version!=data.current_lock_version or previous.lock_version!=data.previous_lock_version:raise OrderingAdjustmentVersionConflictError()
        lines=self.repository.lines_for_sheets([sheet_id,data.previous_sheet_id]);by_sheet=defaultdict(list)
        for line in lines:by_sheet[line.sheet_id].append(line)
        return self._reuse_loaded(current,previous,by_sheet[current.id],by_sheet[previous.id],data.menu_pairs)

    def reuse(self,sheet_id,data,actor_id):
        try:
            if sheet_id==data.previous_sheet_id:raise OrderingAdjustmentReuseError("SAME_SHEET_NOT_ALLOWED")
            sheets=self.repository.sheets([sheet_id,data.previous_sheet_id],True);by_id={sheet.id:sheet for sheet in sheets}
            current=by_id.get(sheet_id);previous=by_id.get(data.previous_sheet_id)
            if not current or not previous:raise OrderingAdjustmentNotFoundError()
            if current.lock_version!=data.current_lock_version or previous.lock_version!=data.previous_lock_version:raise OrderingAdjustmentVersionConflictError()
            lines=self.repository.lines_for_sheets([sheet_id,data.previous_sheet_id],True);by_sheet=defaultdict(list)
            for line in lines:by_sheet[line.sheet_id].append(line)
            preview=self._reuse_loaded(current,previous,by_sheet[current.id],by_sheet[previous.id],data.menu_pairs,lock_source=True)
            safe={item["current_line_id"]:item for item in preview["lines"] if item["status"]=="safe_to_reuse"}
            review_required={item["current_line_id"]:item for item in preview["lines"] if _actionable_reuse_review(item)}
            selected=set(data.selected_current_line_ids)
            if selected-set(safe):raise OrderingAdjustmentReuseError("REUSE_SELECTION_NOT_SAFE",line_ids=[str(value) for value in sorted(selected-set(safe),key=str)])
            current_by_id={line.id:line for line in by_sheet[current.id]};before=[];after=[]
            for line_id in data.selected_current_line_ids:
                line=current_by_id[line_id];value=safe[line_id]["reused_quantity"]
                before.append({"id":line.id,"adjusted_quantity":line.adjusted_quantity,"review_required":line.review_required})
                line.adjusted_quantity=value;line.updated_by=actor_id
                after.append({"id":line.id,"adjusted_quantity":value,"review_required":line.review_required,"previous_line_id":safe[line_id]["previous_line_id"]})
            for line_id,item in review_required.items():
                line=current_by_id[line_id]
                if not line.review_required:
                    before.append({"id":line.id,"adjusted_quantity":line.adjusted_quantity,"review_required":False})
                    line.review_required=True;line.updated_by=actor_id
                    after.append({"id":line.id,"adjusted_quantity":line.adjusted_quantity,"review_required":True,"previous_line_id":item["previous_line_id"]})
            current.last_reuse_source_sheet_id=previous.id;current.reuse_applied_at=datetime.now(UTC);current.reuse_applied_by=actor_id
            current.lock_version+=1;current.updated_by=actor_id
            self.audit.record(actor_id=actor_id,action="ordering_adjustment_reuse",entity_type="ordering_adjustment_sheet",entity_id=current.id,entity_label=f"Revision {current.revision}",before_data={"lock_version":data.current_lock_version,"lines":before},after_data={"lock_version":current.lock_version,"previous_sheet_id":previous.id,"lines":after})
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
            items=self.repository.snapshot_items(sheet.baseline_snapshot_id,True)
            _assert_theoretical_totals(plans,items);finals=aggregate_effective_quantities(lines,items)
            for item in items:item.adjusted_quantity=finals[item.id];item.updated_by=actor_id
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

    def delete_draft(self,sheet_id,lock_version,actor_id):
        try:
            sheet,lines=self._loaded(sheet_id,True)
            if sheet.status!="draft":raise OrderingAdjustmentDeleteForbiddenError(sheet.status)
            if sheet.lock_version!=lock_version:raise OrderingAdjustmentVersionConflictError()
            if self.repository.purchase(sheet.baseline_snapshot_id):raise OrderingAdjustmentSnapshotLockedError()
            snapshot=self.repository.snapshot_for_update(sheet.baseline_snapshot_id)
            owner=self.repository.sheet_for_snapshot(sheet.baseline_snapshot_id)
            if snapshot is None or snapshot.snapshot_kind!="ordering_adjustment" or owner is None or owner.id!=sheet.id:
                raise OrderingAdjustmentInvariantError()
            before={"status":sheet.status,"lock_version":sheet.lock_version,"baseline_snapshot_id":sheet.baseline_snapshot_id,"line_count":len(lines)}
            self.audit.record(actor_id=actor_id,action="ordering_adjustment_delete",entity_type="ordering_adjustment_sheet",entity_id=sheet.id,entity_label=f"Revision {sheet.revision}",before_data=before,after_data={"deleted":True})
            self.repository.delete_owned_draft(sheet.id,sheet.baseline_snapshot_id)
            self.session.commit()
        except Exception:self.session.rollback();raise

    def _assert_mutable(self,sheet,lock_version):
        if sheet.status!="draft":raise OrderingAdjustmentStateError()
        if sheet.lock_version!=lock_version:raise OrderingAdjustmentVersionConflictError()
        if self.repository.purchase(sheet.baseline_snapshot_id):raise OrderingAdjustmentSnapshotLockedError()

    def list(self,page,page_size,status=None,menu_id=None,start_date=None,end_date=None):
        rows,total=self.repository.listing(page,page_size,status,menu_id,start_date,end_date)
        draft_criteria={sheet.id:RequirementCriteria.model_validate(snapshot.criteria) for sheet,snapshot,_ in rows if sheet.status=="draft"}
        live_rows=[]
        if draft_criteria:
            menu_ids=sorted({menu_id for criteria in draft_criteria.values() for menu_id in criteria.menu_ids},key=str)
            live_rows=RequirementRepository(self.session).source_rows(RequirementCriteria(menu_ids=menu_ids))
        values=[]
        for sheet,snapshot,created_by_name in rows:
            data={column.name:getattr(sheet,column.name) for column in sheet.__table__.columns}
            stale=False
            criteria=draft_criteria.get(sheet.id)
            if criteria is not None:
                selected=[]
                for row in live_rows:
                    if row["menu_id"] not in criteria.menu_ids:continue
                    date_selected=(row["menu_date"] in criteria.selected_dates) if criteria.selected_dates is not None else (
                        criteria.start_date<=row["menu_date"]<=criteria.end_date if criteria.start_date is not None else True
                    )
                    if date_selected:selected.append(row)
                stale=_source_fingerprint(criteria,_source_plan(selected))!=sheet.source_fingerprint
            data.update(criteria=snapshot.criteria,source_menus=snapshot.source_menus,created_by_name=created_by_name,stale=stale)
            values.append(data)
        return values,total
