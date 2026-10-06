import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.domains.auth.dependencies import get_current_user
from app.domains.order_adjustments.exceptions import (
    OrderingAdjustmentAlreadyConfirmedError, OrderingAdjustmentDeleteForbiddenError, OrderingAdjustmentExistingDraftError,
    OrderingAdjustmentInvariantError, OrderingAdjustmentLineNotFoundError,
    OrderingAdjustmentNotFoundError, OrderingAdjustmentSnapshotLockedError,
    OrderingAdjustmentReuseError,
    OrderingAdjustmentStaleError, OrderingAdjustmentStateError,
    OrderingAdjustmentVersionConflictError,
)
from app.domains.order_adjustments.schemas import OrderingAdjustmentAction, OrderingAdjustmentBatchUpdate, OrderingAdjustmentCreate, OrderingAdjustmentDetail, OrderingAdjustmentList, OrderingAdjustmentReuseApplyRequest, OrderingAdjustmentReusePreview, OrderingAdjustmentReusePreviewRequest, OrderingAdjustmentSummary
from app.domains.order_adjustments.service import OrderingAdjustmentService
from app.domains.snapshots.exceptions import DuplicateSnapshotError, EmptySnapshotError
from app.domains.users.models import User
from app.shared.schemas import PaginationMeta


router=APIRouter(prefix="/order-adjustments",tags=["order-adjustments"])


def mapped(exc):
    if isinstance(exc,OrderingAdjustmentNotFoundError):return HTTPException(404,"Ordering adjustment sheet not found")
    if isinstance(exc,OrderingAdjustmentLineNotFoundError):return HTTPException(404,"Ordering adjustment line not found")
    if isinstance(exc,OrderingAdjustmentVersionConflictError):return HTTPException(409,detail={"code":"LOCK_VERSION_CONFLICT"})
    if isinstance(exc,OrderingAdjustmentStateError):return HTTPException(409,detail={"code":"INVALID_ADJUSTMENT_STATUS"})
    if isinstance(exc,OrderingAdjustmentSnapshotLockedError):return HTTPException(409,detail={"code":"SNAPSHOT_LOCKED"})
    if isinstance(exc,OrderingAdjustmentDeleteForbiddenError):
        code="CONFIRMED_DELETE_FORBIDDEN" if exc.status=="confirmed" else "CANCELLED_DELETE_FORBIDDEN"
        return HTTPException(409,detail={"code":code})
    if isinstance(exc,OrderingAdjustmentStaleError):return HTTPException(409,detail={"code":"ADJUSTMENT_STALE","reasons":exc.reasons})
    if isinstance(exc,OrderingAdjustmentExistingDraftError):return HTTPException(409,detail={"code":"ADJUSTMENT_DRAFT_EXISTS","existing_sheet_id":str(exc.sheet_id)})
    if isinstance(exc,OrderingAdjustmentAlreadyConfirmedError):return HTTPException(409,detail={"code":"ADJUSTMENT_ALREADY_CONFIRMED","existing_sheet_id":str(exc.sheet_id)})
    if isinstance(exc,OrderingAdjustmentReuseError):return HTTPException(409,detail={"code":exc.code,**exc.details})
    if isinstance(exc,OrderingAdjustmentInvariantError):return HTTPException(422,detail={"code":"SOURCE_TOTAL_MISMATCH"})
    if isinstance(exc,DuplicateSnapshotError):return HTTPException(409,detail={"code":"DUPLICATE_SNAPSHOT","existing_snapshot_id":str(exc.snapshot_id) if exc.snapshot_id else None})
    if isinstance(exc,EmptySnapshotError):return HTTPException(422,"Requirement calculation has no rows to adjust")
    return HTTPException(400,"Ordering adjustment operation failed")


@router.post("",response_model=OrderingAdjustmentDetail,status_code=status.HTTP_201_CREATED)
def create(data:OrderingAdjustmentCreate,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return OrderingAdjustmentDetail.model_validate(OrderingAdjustmentService(session).create(data.criteria,user.id,data.notes))
    except Exception as exc:raise mapped(exc) from exc


@router.get("",response_model=OrderingAdjustmentList)
def listing(session:Annotated[Session,Depends(get_db_session)],user:Annotated[User,Depends(get_current_user)],page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),adjustment_status:str|None=Query(None,alias="status",pattern="^(draft|confirmed|cancelled)$"),menu_id:uuid.UUID|None=None,start_date:date|None=None,end_date:date|None=None):
    if start_date and end_date and start_date>end_date:raise HTTPException(422,"start_date must not follow end_date")
    items,total=OrderingAdjustmentService(session).list(page,page_size,adjustment_status,menu_id,start_date,end_date)
    return OrderingAdjustmentList(items=[OrderingAdjustmentSummary.model_validate(item) for item in items],pagination=PaginationMeta(page=page,page_size=page_size,total=total))


@router.get("/{sheet_id}",response_model=OrderingAdjustmentDetail)
def detail(sheet_id:uuid.UUID,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return OrderingAdjustmentDetail.model_validate(OrderingAdjustmentService(session).detail(sheet_id))
    except Exception as exc:raise mapped(exc) from exc


@router.patch("/{sheet_id}/lines",response_model=OrderingAdjustmentDetail)
def update_lines(sheet_id:uuid.UUID,data:OrderingAdjustmentBatchUpdate,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return OrderingAdjustmentDetail.model_validate(OrderingAdjustmentService(session).update_lines(sheet_id,data.lines,data.lock_version,user.id))
    except Exception as exc:raise mapped(exc) from exc


@router.post("/{sheet_id}/reuse-preview",response_model=OrderingAdjustmentReusePreview)
def reuse_preview(sheet_id:uuid.UUID,data:OrderingAdjustmentReusePreviewRequest,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return OrderingAdjustmentReusePreview.model_validate(OrderingAdjustmentService(session).reuse_preview(sheet_id,data))
    except Exception as exc:raise mapped(exc) from exc


@router.post("/{sheet_id}/reuse",response_model=OrderingAdjustmentDetail)
def reuse(sheet_id:uuid.UUID,data:OrderingAdjustmentReuseApplyRequest,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return OrderingAdjustmentDetail.model_validate(OrderingAdjustmentService(session).reuse(sheet_id,data,user.id))
    except Exception as exc:raise mapped(exc) from exc


@router.post("/{sheet_id}/confirm",response_model=OrderingAdjustmentDetail)
def confirm(sheet_id:uuid.UUID,data:OrderingAdjustmentAction,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return OrderingAdjustmentDetail.model_validate(OrderingAdjustmentService(session).confirm(sheet_id,data.lock_version,user.id))
    except Exception as exc:raise mapped(exc) from exc


@router.delete("/{sheet_id}",status_code=status.HTTP_204_NO_CONTENT)
def delete_draft(sheet_id:uuid.UUID,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)],lock_version:int=Query(...,ge=1)):
    try:
        OrderingAdjustmentService(session).delete_draft(sheet_id,lock_version,user.id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as exc:raise mapped(exc) from exc


@router.post("/{sheet_id}/cancel",response_model=OrderingAdjustmentDetail)
def cancel(sheet_id:uuid.UUID,data:OrderingAdjustmentAction,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return OrderingAdjustmentDetail.model_validate(OrderingAdjustmentService(session).cancel(sheet_id,data.lock_version,user.id))
    except Exception as exc:raise mapped(exc) from exc
