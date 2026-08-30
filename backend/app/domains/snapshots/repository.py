import uuid
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.domains.snapshots.models import RequirementSnapshot,RequirementSnapshotItem
from app.domains.users.models import User

class SnapshotRepository:
    def __init__(self,session:Session):self.session=session
    def add(self,value):self.session.add(value)
    def by_fingerprint(self,value):return self.session.scalar(select(RequirementSnapshot).where(RequirementSnapshot.fingerprint==value))
    def by_content(self,criteria_fingerprint,content_fingerprint):return self.session.scalar(select(RequirementSnapshot).where(RequirementSnapshot.criteria_fingerprint==criteria_fingerprint,RequirementSnapshot.content_fingerprint==content_fingerprint))
    def next_revision(self,criteria_fingerprint):return (self.session.scalar(select(func.max(RequirementSnapshot.revision)).where(RequirementSnapshot.criteria_fingerprint==criteria_fingerprint)) or 0)+1
    def get(self,snapshot_id):return self.session.get(RequirementSnapshot,snapshot_id)
    def item(self,snapshot_id,item_id):return self.session.scalar(select(RequirementSnapshotItem).where(RequirementSnapshotItem.snapshot_id==snapshot_id,RequirementSnapshotItem.id==item_id))
    def detail(self,snapshot_id):
        header=self.session.execute(select(RequirementSnapshot,User.display_name).join(User,User.id==RequirementSnapshot.created_by).where(RequirementSnapshot.id==snapshot_id)).first()
        if not header:return None,[]
        items=list(self.session.scalars(select(RequirementSnapshotItem).where(RequirementSnapshotItem.snapshot_id==snapshot_id).order_by(RequirementSnapshotItem.supplier_name_snapshot,RequirementSnapshotItem.ingredient_code_snapshot)))
        return header,items
    def list(self,page,page_size,created_by=None,start_at=None,end_before=None):
        where=[]
        if created_by:where.append(RequirementSnapshot.created_by==created_by)
        if start_at:where.append(RequirementSnapshot.created_at>=start_at)
        if end_before:where.append(RequirementSnapshot.created_at<end_before)
        total=self.session.scalar(select(func.count()).select_from(RequirementSnapshot).where(*where)) or 0
        rows=self.session.execute(select(RequirementSnapshot,User.display_name).join(User,User.id==RequirementSnapshot.created_by).where(*where).order_by(RequirementSnapshot.created_at.desc(),RequirementSnapshot.id).offset((page-1)*page_size).limit(page_size)).all()
        return rows,total
    def delete(self,value):self.session.delete(value)
