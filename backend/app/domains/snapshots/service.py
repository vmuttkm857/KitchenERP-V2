from decimal import Decimal
from sqlalchemy.exc import IntegrityError
from app.domains.requirements.service import RequirementService
from app.domains.snapshots.exceptions import DuplicateSnapshotError,EmptySnapshotError,SnapshotNotFoundError
from app.domains.snapshots.fingerprint import normalize,snapshot_fingerprint
from app.domains.snapshots.models import RequirementSnapshot,RequirementSnapshotItem
from app.domains.snapshots.repository import SnapshotRepository

class SnapshotService:
    def __init__(self,session):self.session=session;self.repository=SnapshotRepository(session)
    def create(self,criteria,actor_id):
        normalized=normalize(criteria.model_dump(exclude_none=True));fingerprint=snapshot_fingerprint(normalized)
        existing=self.repository.by_fingerprint(fingerprint)
        if existing:raise DuplicateSnapshotError(existing.id)
        try:
            result=RequirementService(self.session).calculate(criteria)
            if not result["rows"]:raise EmptySnapshotError()
            header=RequirementSnapshot(fingerprint=fingerprint,criteria=normalized,source_menus=normalize(result["source_menus"]),anomaly_snapshot=normalize(result["anomalies"]),anomaly_summary=result["anomaly_summary"],known_estimated_cost=result["known_estimated_cost"],total_estimated_cost=result["total_estimated_cost"],created_by=actor_id)
            self.repository.add(header);self.session.flush()
            for row in result["rows"]:
                related=[a for a in result["anomalies"] if str(a.get("related_entity_id")) in {str(row["ingredient_id"])} or str(a.get("context",{}).get("ingredient_id"))==str(row["ingredient_id"])]
                self.repository.add(RequirementSnapshotItem(snapshot_id=header.id,row_key=row["row_key"],ingredient_id=row["ingredient_id"],ingredient_code_snapshot=row["ingredient_code"],ingredient_name_snapshot=row["ingredient_name"],supplier_id=row["supplier_id"],supplier_code_snapshot=row.get("supplier_code"),supplier_name_snapshot=row["supplier_name"],requirement_quantity=row["requirement_quantity"],requirement_unit=row["requirement_unit"],suggested_purchase_quantity=row["suggested_purchase_quantity"],adjusted_quantity=row["suggested_purchase_quantity"],suggested_purchase_unit_snapshot=row["suggested_purchase_unit"],purchase_unit_snapshot=row["configured_purchase_unit"],package_size_snapshot=row["package_size"],minimum_order_quantity_snapshot=row["minimum_order_quantity"],unit_price_snapshot=row["current_price"],estimated_cost_snapshot=row["estimated_cost"],needs_review=row["needs_review"],total_diner_count=row["total_diner_count"],source_count=row["source_count"],anomaly_snapshot=normalize(related),source_summary=normalize(row["schedules"]),updated_by=actor_id))
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback();existing=self.repository.by_fingerprint(fingerprint);raise DuplicateSnapshotError(existing.id if existing else None) from exc
        except Exception:
            self.session.rollback();raise
        return self.detail(header.id)
    def detail(self,snapshot_id):
        header,items=self.repository.detail(snapshot_id)
        if not header:raise SnapshotNotFoundError()
        value,created_by_name=header
        data={column.name:getattr(value,column.name) for column in value.__table__.columns};data["created_by_name"]=created_by_name;data["items"]=items;return data
    def list(self,page,page_size,created_by=None):
        rows,total=self.repository.list(page,page_size,created_by);return [dict({column.name:getattr(row[0],column.name) for column in row[0].__table__.columns},created_by_name=row[1]) for row in rows],total
    def update_adjusted(self,snapshot_id,item_id,quantity,actor_id):
        item=self.repository.item(snapshot_id,item_id)
        if not item:raise SnapshotNotFoundError()
        item.adjusted_quantity=Decimal(quantity);item.updated_by=actor_id;self.session.commit();return item
