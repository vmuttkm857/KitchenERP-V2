import uuid
from collections import defaultdict
from datetime import UTC,datetime
from decimal import Decimal
from sqlalchemy.exc import IntegrityError
from app.domains.purchases.calculator import purchase_values
from app.domains.purchases.exceptions import DuplicatePurchaseError,InvalidPurchaseStatusError,PurchaseNotFoundError,SnapshotNotReadyError
from app.domains.purchases.models import PurchaseBatch,PurchaseOrder,PurchaseOrderItem
from app.domains.purchases.repository import PurchaseRepository
from app.domains.snapshots.service import SnapshotService

class PurchaseService:
    def __init__(self,session):self.session=session;self.repository=PurchaseRepository(session)
    def create(self,snapshot_id,actor_id,notes=None):
        existing=self.repository.batch_for_snapshot(snapshot_id)
        if existing:raise DuplicatePurchaseError(existing.id)
        snapshot=self.repository.snapshot(snapshot_id)
        if not snapshot:raise PurchaseNotFoundError()
        items=self.repository.snapshot_items(snapshot_id);issues=SnapshotService(self.session).readiness(items)
        if issues:raise SnapshotNotReadyError(issues)
        batch_id=uuid.uuid4();number=f"PO-{datetime.now(UTC):%Y%m%d}-{batch_id.hex[:8].upper()}"
        try:
            prepared=[];all_warnings=[]
            for item in items:
                final,cost,warnings=purchase_values(item);prepared.append((item,final,cost,warnings));all_warnings.extend([{**warning,"source_snapshot_item_id":str(item.id)} for warning in warnings])
            known=sum((cost or Decimal("0") for _,_,cost,_ in prepared),Decimal("0"));total=None if any(cost is None for _,_,cost,_ in prepared) else known
            batch=PurchaseBatch(id=batch_id,purchase_number=number,source_snapshot_id=snapshot.id,source_snapshot_revision=snapshot.revision,source_summary_snapshot=snapshot.source_menus,status="draft",known_total_cost=known,total_cost=total,anomaly_snapshot=all_warnings,notes=notes,created_by=actor_id,updated_by=actor_id)
            self.repository.add(batch);self.session.flush();grouped=defaultdict(list)
            for value in prepared:grouped[value[0].supplier_id].append(value)
            for supplier_id,group in grouped.items():
                group_known=sum((cost or Decimal("0") for _,_,cost,_ in group),Decimal("0"));group_total=None if any(cost is None for _,_,cost,_ in group) else group_known;first=group[0][0]
                order=PurchaseOrder(batch_id=batch.id,supplier_id=supplier_id,supplier_code_snapshot=first.supplier_code_snapshot,supplier_name_snapshot=first.supplier_name_snapshot,known_total_cost=group_known,total_cost=group_total)
                self.repository.add(order);self.session.flush()
                for item,final,cost,warnings in group:
                    self.repository.add(PurchaseOrderItem(purchase_order_id=order.id,source_snapshot_item_id=item.id,ingredient_id=item.ingredient_id,ingredient_code_snapshot=item.ingredient_code_snapshot,ingredient_name_snapshot=item.ingredient_name_snapshot,supplier_id=item.supplier_id,supplier_code_snapshot=item.supplier_code_snapshot,supplier_name_snapshot=item.supplier_name_snapshot,requirement_quantity_snapshot=item.requirement_quantity,requirement_unit_snapshot=item.requirement_unit,suggested_quantity_snapshot=item.suggested_purchase_quantity,adjusted_quantity_snapshot=item.adjusted_quantity,final_purchase_quantity=final,purchase_unit_snapshot=item.purchase_unit_snapshot,package_size_snapshot=item.package_size_snapshot,minimum_order_quantity_snapshot=item.minimum_order_quantity_snapshot,unit_price_snapshot=item.unit_price_snapshot,purchase_cost_snapshot=cost,anomaly_snapshot=item.anomaly_snapshot+warnings,source_summary_snapshot=item.source_summary))
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback();existing=self.repository.batch_for_snapshot(snapshot_id);raise DuplicatePurchaseError(existing.id if existing else None) from exc
        except Exception:self.session.rollback();raise
        return self.detail(batch.id)
    def detail(self,batch_id):
        header,orders,items=self.repository.detail(batch_id)
        if not header:raise PurchaseNotFoundError()
        batch,creator=header;by_order=defaultdict(list)
        for item in items:by_order[item.purchase_order_id].append(item)
        data={column.name:getattr(batch,column.name) for column in batch.__table__.columns};data["created_by_name"]=creator
        data["supplier_summary"]=[{"supplier_id":order.supplier_id,"supplier_code":order.supplier_code_snapshot,"supplier_name":order.supplier_name_snapshot} for order in orders]
        data["orders"]=[dict({column.name:getattr(order,column.name) for column in order.__table__.columns},items=by_order[order.id]) for order in orders];return data
    def list(self,page,page_size,status=None,supplier_id=None,search=None,start_date=None,end_date=None):
        rows,total,suppliers=self.repository.list(page,page_size,status,supplier_id,search,start_date,end_date);by_batch=defaultdict(list)
        for batch_id,supplier_id_value,code,name in suppliers:by_batch[batch_id].append({"supplier_id":supplier_id_value,"supplier_code":code,"supplier_name":name})
        return [dict({column.name:getattr(row[0],column.name) for column in row[0].__table__.columns},created_by_name=row[1],supplier_summary=by_batch[row[0].id],orders=[]) for row in rows],total
    def transition(self,batch_id,target,actor_id):
        batch=self.repository.batch(batch_id)
        if not batch:raise PurchaseNotFoundError()
        now=datetime.now(UTC)
        if target=="confirmed":
            if batch.status!="draft":raise InvalidPurchaseStatusError()
            batch.status="confirmed";batch.confirmed_at=now
        elif target=="cancelled":
            if batch.status not in {"draft","confirmed"}:raise InvalidPurchaseStatusError()
            batch.status="cancelled";batch.cancelled_at=now
        else:raise InvalidPurchaseStatusError()
        batch.updated_by=actor_id;self.session.commit();return self.detail(batch.id)
