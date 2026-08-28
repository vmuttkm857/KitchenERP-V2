import uuid
from datetime import date
from typing import Annotated,Literal
from fastapi import APIRouter,Depends,HTTPException,Query,status
from sqlalchemy.orm import Session
from app.api.dependencies import get_db_session
from app.domains.auth.dependencies import get_current_user
from app.domains.purchases.exceptions import DuplicatePurchaseError,InvalidPurchaseStatusError,PurchaseNotFoundError,SnapshotNotReadyError
from app.domains.purchases.schemas import PurchaseCreate,PurchaseList,PurchasePublic
from app.domains.purchases.service import PurchaseService
from app.domains.users.models import User
from app.shared.schemas import PaginationMeta
router=APIRouter(prefix="/purchases",tags=["purchases"])
def mapped(exc):
    if isinstance(exc,PurchaseNotFoundError):return HTTPException(404,"Snapshot or purchase not found")
    if isinstance(exc,DuplicatePurchaseError):return HTTPException(409,detail={"code":"DUPLICATE_PURCHASE","existing_purchase_id":str(exc.purchase_id) if exc.purchase_id else None})
    if isinstance(exc,SnapshotNotReadyError):return HTTPException(422,detail={"code":"SNAPSHOT_NOT_READY","blocking_issues":exc.issues})
    if isinstance(exc,InvalidPurchaseStatusError):return HTTPException(409,detail={"code":"INVALID_PURCHASE_STATUS"})
    return HTTPException(400,"Purchase operation failed")
@router.post("",response_model=PurchasePublic,status_code=status.HTTP_201_CREATED)
def create(data:PurchaseCreate,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return PurchasePublic.model_validate(PurchaseService(session).create(data.snapshot_id,user.id,data.notes))
    except Exception as exc:raise mapped(exc) from exc
@router.get("",response_model=PurchaseList)
def listing(session:Annotated[Session,Depends(get_db_session)],user:Annotated[User,Depends(get_current_user)],page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),purchase_status:Literal["draft","confirmed","cancelled"]|None=None,supplier_id:uuid.UUID|None=None,search:str|None=None,start_date:date|None=None,end_date:date|None=None):
    items,total=PurchaseService(session).list(page,page_size,purchase_status,supplier_id,search,start_date,end_date);return PurchaseList(items=[PurchasePublic.model_validate(item) for item in items],pagination=PaginationMeta(page=page,page_size=page_size,total=total))
@router.get("/{purchase_id}",response_model=PurchasePublic)
def detail(purchase_id:uuid.UUID,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return PurchasePublic.model_validate(PurchaseService(session).detail(purchase_id))
    except Exception as exc:raise mapped(exc) from exc
@router.post("/{purchase_id}/confirm",response_model=PurchasePublic)
def confirm(purchase_id:uuid.UUID,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return PurchasePublic.model_validate(PurchaseService(session).transition(purchase_id,"confirmed",user.id))
    except Exception as exc:raise mapped(exc) from exc
@router.post("/{purchase_id}/cancel",response_model=PurchasePublic)
def cancel(purchase_id:uuid.UUID,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return PurchasePublic.model_validate(PurchaseService(session).transition(purchase_id,"cancelled",user.id))
    except Exception as exc:raise mapped(exc) from exc
