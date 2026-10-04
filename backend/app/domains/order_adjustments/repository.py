from sqlalchemy import func, select

from app.domains.order_adjustments.models import OrderingAdjustmentLine, OrderingAdjustmentSheet
from app.domains.purchases.models import PurchaseBatch
from app.domains.snapshots.models import RequirementSnapshot, RequirementSnapshotItem
from app.domains.users.models import User


class OrderingAdjustmentRepository:
    def __init__(self,session): self.session=session
    def add(self,value): self.session.add(value)
    def sheet(self,sheet_id,for_update=False):
        statement=select(OrderingAdjustmentSheet).where(OrderingAdjustmentSheet.id==sheet_id)
        if for_update: statement=statement.with_for_update()
        return self.session.scalar(statement)
    def sheet_for_snapshot(self,snapshot_id):
        return self.session.scalar(select(OrderingAdjustmentSheet).where(OrderingAdjustmentSheet.baseline_snapshot_id==snapshot_id))
    def lock_creation_key(self,criteria_fingerprint):
        value=int(criteria_fingerprint[:16],16)
        if value>=2**63:value-=2**64
        self.session.execute(select(func.pg_advisory_xact_lock(value)))
    def sheet_for_source(self,criteria_fingerprint,source_fingerprint,statuses):
        return self.session.scalar(select(OrderingAdjustmentSheet).where(OrderingAdjustmentSheet.criteria_fingerprint==criteria_fingerprint,OrderingAdjustmentSheet.source_fingerprint==source_fingerprint,OrderingAdjustmentSheet.status.in_(statuses)).order_by(OrderingAdjustmentSheet.created_at.desc()))
    def lines(self,sheet_id,for_update=False):
        statement=select(OrderingAdjustmentLine).where(OrderingAdjustmentLine.sheet_id==sheet_id).order_by(OrderingAdjustmentLine.source_menu_id,OrderingAdjustmentLine.requirement_date,OrderingAdjustmentLine.meal_type_sort_order_snapshot,OrderingAdjustmentLine.source_meal_type_id,OrderingAdjustmentLine.menu_dish_sort_order_snapshot,OrderingAdjustmentLine.source_menu_dish_id,OrderingAdjustmentLine.dish_ingredient_sort_order_snapshot,OrderingAdjustmentLine.source_dish_ingredient_id)
        if for_update: statement=statement.with_for_update()
        return list(self.session.scalars(statement))
    def snapshot(self,snapshot_id): return self.session.get(RequirementSnapshot,snapshot_id)
    def snapshot_items(self,snapshot_id,for_update=False):
        statement=select(RequirementSnapshotItem).where(RequirementSnapshotItem.snapshot_id==snapshot_id)
        if for_update: statement=statement.with_for_update()
        return list(self.session.scalars(statement))
    def purchase(self,snapshot_id): return self.session.scalar(select(PurchaseBatch).where(PurchaseBatch.source_snapshot_id==snapshot_id))
    def listing(self,page,page_size,status=None,menu_id=None,start_date=None,end_date=None):
        filters=[]
        if status:filters.append(OrderingAdjustmentSheet.status==status)
        line_filters=[]
        if menu_id:line_filters.append(OrderingAdjustmentLine.source_menu_id==menu_id)
        if start_date:line_filters.append(OrderingAdjustmentLine.requirement_date>=start_date)
        if end_date:line_filters.append(OrderingAdjustmentLine.requirement_date<=end_date)
        if line_filters:filters.append(OrderingAdjustmentSheet.id.in_(select(OrderingAdjustmentLine.sheet_id).where(*line_filters)))
        total=self.session.scalar(select(func.count()).select_from(OrderingAdjustmentSheet).where(*filters)) or 0
        rows=self.session.execute(select(OrderingAdjustmentSheet,RequirementSnapshot,User.display_name).join(RequirementSnapshot,RequirementSnapshot.id==OrderingAdjustmentSheet.baseline_snapshot_id).join(User,User.id==OrderingAdjustmentSheet.created_by).where(*filters).order_by(OrderingAdjustmentSheet.updated_at.desc(),OrderingAdjustmentSheet.id).offset((page-1)*page_size).limit(page_size)).all()
        return rows,total
