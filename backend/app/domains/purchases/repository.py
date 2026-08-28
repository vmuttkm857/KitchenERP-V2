from sqlalchemy import func,or_,select
from app.domains.purchases.models import PurchaseBatch,PurchaseOrder,PurchaseOrderItem
from app.domains.snapshots.models import RequirementSnapshot,RequirementSnapshotItem
from app.domains.users.models import User

class PurchaseRepository:
    def __init__(self,session):self.session=session
    def add(self,value):self.session.add(value)
    def batch_for_snapshot(self,snapshot_id):return self.session.scalar(select(PurchaseBatch).where(PurchaseBatch.source_snapshot_id==snapshot_id))
    def batch(self,batch_id):return self.session.get(PurchaseBatch,batch_id)
    def snapshot(self,snapshot_id):return self.session.get(RequirementSnapshot,snapshot_id)
    def snapshot_items(self,snapshot_id):return list(self.session.scalars(select(RequirementSnapshotItem).where(RequirementSnapshotItem.snapshot_id==snapshot_id).order_by(RequirementSnapshotItem.supplier_name_snapshot,RequirementSnapshotItem.ingredient_code_snapshot)))
    def detail(self,batch_id):
        header=self.session.execute(select(PurchaseBatch,User.display_name).join(User,User.id==PurchaseBatch.created_by).where(PurchaseBatch.id==batch_id)).first()
        if not header:return None,[],[]
        orders=list(self.session.scalars(select(PurchaseOrder).where(PurchaseOrder.batch_id==batch_id).order_by(PurchaseOrder.supplier_name_snapshot)))
        order_ids=[order.id for order in orders]
        items=list(self.session.scalars(select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id.in_(order_ids)).order_by(PurchaseOrderItem.supplier_name_snapshot,PurchaseOrderItem.ingredient_code_snapshot))) if order_ids else []
        return header,orders,items
    def list(self,page,page_size,status=None,supplier_id=None,search=None,start_date=None,end_date=None):
        filters=[]
        if status:filters.append(PurchaseBatch.status==status)
        if supplier_id:filters.append(PurchaseBatch.id.in_(select(PurchaseOrder.batch_id).where(PurchaseOrder.supplier_id==supplier_id)))
        if search:filters.append(PurchaseBatch.purchase_number.ilike(f"%{search.strip()}%"))
        if start_date:filters.append(func.date(PurchaseBatch.created_at)>=start_date)
        if end_date:filters.append(func.date(PurchaseBatch.created_at)<=end_date)
        total=self.session.scalar(select(func.count()).select_from(PurchaseBatch).where(*filters)) or 0
        rows=self.session.execute(select(PurchaseBatch,User.display_name).join(User,User.id==PurchaseBatch.created_by).where(*filters).order_by(PurchaseBatch.created_at.desc(),PurchaseBatch.id).offset((page-1)*page_size).limit(page_size)).all()
        batch_ids=[row[0].id for row in rows]
        suppliers=self.session.execute(select(PurchaseOrder.batch_id,PurchaseOrder.supplier_id,PurchaseOrder.supplier_code_snapshot,PurchaseOrder.supplier_name_snapshot).where(PurchaseOrder.batch_id.in_(batch_ids)).order_by(PurchaseOrder.supplier_name_snapshot)).all() if batch_ids else []
        return rows,total,suppliers
