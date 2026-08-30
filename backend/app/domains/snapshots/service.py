from datetime import UTC,date,datetime,time,timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from sqlalchemy.exc import IntegrityError
from app.domains.requirements.service import RequirementService
from app.domains.snapshots.exceptions import DuplicateSnapshotError,EmptySnapshotError,InvalidPurchaseUnitError,InvalidSnapshotDateRangeError,SnapshotInUseError,SnapshotLockedError,SnapshotNotFoundError
from app.domains.snapshots.fingerprint import content_fingerprint,hash_payload,normalize,snapshot_fingerprint
from app.domains.snapshots.models import RequirementSnapshot,RequirementSnapshotItem
from app.domains.snapshots.repository import SnapshotRepository
from app.domains.auth.service import AuthService
from app.shared.domain.quantities import convert_quantity

class SnapshotService:
    def __init__(self,session):self.session=session;self.repository=SnapshotRepository(session)
    def create(self,criteria,actor_id):
        normalized=normalize(criteria.model_dump(exclude_none=True));criteria_hash=snapshot_fingerprint(normalized)
        try:
            result=RequirementService(self.session).calculate(criteria)
            if not result["rows"]:raise EmptySnapshotError()
            content_hash=content_fingerprint(result);existing=self.repository.by_content(criteria_hash,content_hash)
            if existing:raise DuplicateSnapshotError(existing.id)
            revision=self.repository.next_revision(criteria_hash)
            header=RequirementSnapshot(fingerprint=hash_payload({"criteria":criteria_hash,"content":content_hash}),criteria_fingerprint=criteria_hash,content_fingerprint=content_hash,revision=revision,criteria=normalized,source_menus=normalize(result["source_menus"]),anomaly_snapshot=normalize(result["anomalies"]),anomaly_summary=result["anomaly_summary"],known_estimated_cost=result["known_estimated_cost"],total_estimated_cost=result["total_estimated_cost"],created_by=actor_id)
            self.repository.add(header);self.session.flush()
            for row in result["rows"]:
                related=[a for a in result["anomalies"] if str(a.get("related_entity_id")) in {str(row["ingredient_id"])} or str(a.get("context",{}).get("ingredient_id"))==str(row["ingredient_id"])]
                self.repository.add(RequirementSnapshotItem(snapshot_id=header.id,row_key=row["row_key"],ingredient_id=row["ingredient_id"],ingredient_code_snapshot=row["ingredient_code"],ingredient_name_snapshot=row["ingredient_name"],supplier_id=row["supplier_id"],supplier_code_snapshot=row.get("supplier_code"),supplier_name_snapshot=row["supplier_name"],requirement_quantity=row["requirement_quantity"],requirement_unit=row["requirement_unit"],suggested_purchase_quantity=row["suggested_purchase_quantity"],adjusted_quantity=row["suggested_purchase_quantity"],suggested_purchase_unit_snapshot=row["suggested_purchase_unit"],purchase_unit_snapshot=row["suggested_purchase_unit"],configured_purchase_unit_snapshot=row["configured_purchase_unit"],package_size_snapshot=row["package_size"],minimum_order_quantity_snapshot=row["minimum_order_quantity"],unit_price_snapshot=row["current_price"],estimated_cost_snapshot=row["estimated_cost"],needs_review=row["needs_review"],total_diner_count=row["total_diner_count"],source_count=row["source_count"],anomaly_snapshot=normalize(related),source_summary=normalize(row["schedules"]),updated_by=actor_id))
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback();existing=self.repository.by_content(criteria_hash,content_hash);raise DuplicateSnapshotError(existing.id if existing else None) from exc
        except Exception:
            self.session.rollback();raise
        return self.detail(header.id)
    def detail(self,snapshot_id):
        header,items=self.repository.detail(snapshot_id)
        if not header:raise SnapshotNotFoundError()
        value,created_by_name=header
        data={column.name:getattr(value,column.name) for column in value.__table__.columns};data["created_by_name"]=created_by_name
        purchase=self._purchase(value.id);issues=self.readiness(items)
        data.update(locked=purchase is not None,purchase_id=purchase.id if purchase else None,purchase_number=purchase.purchase_number if purchase else None,purchase_ready=purchase is None and not issues,blocking_issues=issues)
        data["items"]=[self._item_data(item) for item in items];return data
    def list(self,page,page_size,created_by=None,start_date:date|None=None,end_date:date|None=None):
        if start_date and end_date and start_date>end_date:raise InvalidSnapshotDateRangeError()
        timezone=ZoneInfo("Asia/Taipei")
        start_at=datetime.combine(start_date,time.min,timezone).astimezone(UTC) if start_date else None
        end_before=datetime.combine(end_date+timedelta(days=1),time.min,timezone).astimezone(UTC) if end_date else None
        rows,total=self.repository.list(page,page_size,created_by,start_at,end_before);return [dict({column.name:getattr(row[0],column.name) for column in row[0].__table__.columns},created_by_name=row[1]) for row in rows],total
    def update_adjusted(self,snapshot_id,item_id,quantity,purchase_unit,actor_id):
        if self._purchase(snapshot_id):raise SnapshotLockedError()
        item=self.repository.item(snapshot_id,item_id)
        if not item:raise SnapshotNotFoundError()
        target=(purchase_unit or item.purchase_unit_snapshot or item.requirement_unit).strip()
        current=item.purchase_unit_snapshot or item.requirement_unit
        original_quantity=item.adjusted_quantity;current_quantity=original_quantity
        if purchase_unit is not None and target!=current:
            if current_quantity is None:raise InvalidPurchaseUnitError()
            converted=convert_quantity(current_quantity,current,target)
            if not converted.convertible or converted.quantity is None:raise InvalidPurchaseUnitError()
            current_quantity=converted.quantity
            if quantity is not None and Decimal(quantity)!=original_quantity:current_quantity=Decimal(quantity)
        elif quantity is not None:current_quantity=Decimal(quantity)
        item.adjusted_quantity=current_quantity;item.purchase_unit_snapshot=target;item.updated_by=actor_id;self.session.commit();return self._item_data(item)
    def readiness(self,items):
        issues=[]
        for item in items:
            if item.supplier_id is None:issues.append({"code":"UNASSIGNED_SUPPLIER","item_id":str(item.id),"message":f"{item.ingredient_name_snapshot} has no supplier"})
            if item.adjusted_quantity is None:issues.append({"code":"MISSING_ADJUSTED_QUANTITY","item_id":str(item.id),"message":f"{item.ingredient_name_snapshot} has no adjusted quantity"})
            if not item.purchase_unit_snapshot:issues.append({"code":"MISSING_PURCHASE_UNIT","item_id":str(item.id),"message":f"{item.ingredient_name_snapshot} has no purchase unit"})
            elif not convert_quantity(item.adjusted_quantity or Decimal("0"),item.purchase_unit_snapshot,item.requirement_unit).convertible:issues.append({"code":"INCOMPATIBLE_PURCHASE_UNIT","item_id":str(item.id),"message":f"{item.ingredient_name_snapshot} purchase unit is incompatible"})
        return issues
    def _item_data(self,item):
        data={column.name:getattr(item,column.name) for column in item.__table__.columns};data["adjusted_estimated_cost"]=self.adjusted_cost(item);return data
    def adjusted_cost(self,item):
        if item.adjusted_quantity is None or item.unit_price_snapshot is None or not item.purchase_unit_snapshot:return None
        converted=convert_quantity(item.adjusted_quantity,item.purchase_unit_snapshot,item.requirement_unit)
        return converted.quantity*item.unit_price_snapshot if converted.convertible and converted.quantity is not None else None
    def _purchase(self,snapshot_id):
        from app.domains.purchases.repository import PurchaseRepository
        return PurchaseRepository(self.session).batch_for_snapshot(snapshot_id)
    def delete(self,snapshot_id,actor_id,password):
        value=self.repository.get(snapshot_id)
        if not value:raise SnapshotNotFoundError()
        if self._purchase(snapshot_id):raise SnapshotInUseError()
        AuthService(self.session).verify_current_password(actor_id,password);self.repository.delete(value);self.session.commit()
