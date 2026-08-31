import uuid
from datetime import date
from typing import Annotated
from fastapi import APIRouter,Depends,HTTPException,Query,Response,status
from sqlalchemy.orm import Session
from app.api.dependencies import get_db_session
from app.domains.auth.dependencies import get_current_user, require_admin
from app.domains.snapshots.exceptions import DuplicateSnapshotError,EmptySnapshotError,InvalidPurchaseUnitError,InvalidSnapshotDateRangeError,SnapshotInUseError,SnapshotLockedError,SnapshotNotFoundError
from app.domains.auth.exceptions import InvalidCredentialsError
from app.domains.snapshots.schemas import SnapshotCreate,SnapshotDetail,SnapshotHeaderPublic,SnapshotItemPublic,SnapshotItemUpdate,SnapshotList
from app.domains.snapshots.service import SnapshotService
from app.domains.users.models import User
from app.shared.schemas import PaginationMeta
from app.shared.schemas import PasswordConfirmation

router=APIRouter(prefix="/requirement-snapshots",tags=["requirement-snapshots"])
def mapped(exc):
    if isinstance(exc,SnapshotNotFoundError):return HTTPException(404,"Snapshot not found")
    if isinstance(exc,DuplicateSnapshotError):return HTTPException(409,detail={"code":"DUPLICATE_SNAPSHOT","existing_snapshot_id":str(exc.snapshot_id) if exc.snapshot_id else None})
    if isinstance(exc,EmptySnapshotError):return HTTPException(422,"Requirement calculation has no rows to snapshot")
    if isinstance(exc,SnapshotLockedError):return HTTPException(409,detail={"code":"SNAPSHOT_LOCKED"})
    if isinstance(exc,InvalidPurchaseUnitError):return HTTPException(422,detail={"code":"INVALID_PURCHASE_UNIT"})
    if isinstance(exc,SnapshotInUseError):return HTTPException(409,detail={"code":"SNAPSHOT_HAS_PURCHASE"})
    if isinstance(exc,InvalidSnapshotDateRangeError):return HTTPException(422,"開始日期不可晚於結束日期")
    if isinstance(exc,InvalidCredentialsError):return HTTPException(401,"Password verification failed")
    return HTTPException(400,"Snapshot operation failed")

@router.post("",response_model=SnapshotDetail,status_code=status.HTTP_201_CREATED)
def create(data:SnapshotCreate,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return SnapshotDetail.model_validate(SnapshotService(session).create(data.criteria,user.id))
    except Exception as exc:raise mapped(exc) from exc

@router.get("",response_model=SnapshotList)
def list_snapshots(session:Annotated[Session,Depends(get_db_session)],user:Annotated[User,Depends(get_current_user)],page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),created_by:uuid.UUID|None=None,start_date:date|None=None,end_date:date|None=None):
    try:
        items,total=SnapshotService(session).list(page,page_size,created_by,start_date,end_date)
        return SnapshotList(items=[SnapshotHeaderPublic.model_validate(item) for item in items],pagination=PaginationMeta(page=page,page_size=page_size,total=total))
    except Exception as exc:raise mapped(exc) from exc

@router.get("/{snapshot_id}",response_model=SnapshotDetail)
def detail(snapshot_id:uuid.UUID,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return SnapshotDetail.model_validate(SnapshotService(session).detail(snapshot_id))
    except Exception as exc:raise mapped(exc) from exc

@router.patch("/{snapshot_id}/items/{item_id}",response_model=SnapshotItemPublic)
def adjust(snapshot_id:uuid.UUID,item_id:uuid.UUID,data:SnapshotItemUpdate,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return SnapshotItemPublic.model_validate(SnapshotService(session).update_adjusted(snapshot_id,item_id,data.adjusted_quantity,data.purchase_unit,user.id))
    except Exception as exc:raise mapped(exc) from exc

@router.post("/{snapshot_id}/hard-delete",status_code=204)
def hard_delete(snapshot_id:uuid.UUID,data:PasswordConfirmation,user:Annotated[User,Depends(require_admin)],session:Annotated[Session,Depends(get_db_session)]):
    try:SnapshotService(session).delete(snapshot_id,user.id,data.password)
    except Exception as exc:raise mapped(exc) from exc
    return Response(status_code=204)
