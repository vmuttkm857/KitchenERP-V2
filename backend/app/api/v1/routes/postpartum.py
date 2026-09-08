import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session
from app.api.dependencies import get_db_session
from app.domains.auth.dependencies import get_current_user
from app.domains.postpartum.exceptions import InvalidPostpartumDataError, PostpartumCaseNotFoundError, PostpartumPauseNotFoundError
from app.domains.postpartum.schemas import CaseCreate, CaseDetail, CaseList, CasePublic, CaseStatus, CaseUpdate, PauseCreate, PausePublic, PauseUpdate, RoomChangeCreate, RoomHistoryPublic
from app.domains.postpartum.service import PostpartumService
from app.domains.users.models import User
from app.shared.schemas import PaginationMeta

router = APIRouter(prefix="/postpartum", tags=["postpartum"], dependencies=[Depends(get_current_user)])

def error(exc):
    if isinstance(exc, (PostpartumCaseNotFoundError, PostpartumPauseNotFoundError)): return HTTPException(404, "Postpartum case resource not found")
    if isinstance(exc, InvalidPostpartumDataError): return HTTPException(422, str(exc))
    return HTTPException(400, "Postpartum operation failed")

@router.get("/cases", response_model=CaseList)
def cases(session: Annotated[Session, Depends(get_db_session)], page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), active: bool | None = None, status_filter: CaseStatus | None = Query(default=None, alias="status"), search: str | None = None):
    try:
        items,total=PostpartumService(session).list(page,page_size,active,status_filter,search)
        return CaseList(items=[CasePublic.model_validate(item) for item in items],pagination=PaginationMeta(page=page,page_size=page_size,total=total))
    except Exception as exc: raise error(exc) from exc

@router.post("/cases",response_model=CasePublic,status_code=201)
def create_case(data:CaseCreate,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return CasePublic.model_validate(PostpartumService(session).create(data,user.id))
    except Exception as exc:raise error(exc) from exc

@router.get("/cases/{case_id}",response_model=CaseDetail)
def case_detail(case_id:uuid.UUID,session:Annotated[Session,Depends(get_db_session)]):
    try:return CaseDetail.model_validate(PostpartumService(session).detail(case_id))
    except Exception as exc:raise error(exc) from exc

@router.patch("/cases/{case_id}",response_model=CasePublic)
def update_case(case_id:uuid.UUID,data:CaseUpdate,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return CasePublic.model_validate(PostpartumService(session).update(case_id,data,user.id))
    except Exception as exc:raise error(exc) from exc

@router.post("/cases/{case_id}/deactivate",response_model=CasePublic)
def deactivate_case(case_id:uuid.UUID,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return CasePublic.model_validate(PostpartumService(session).set_active(case_id,False,user.id))
    except Exception as exc:raise error(exc) from exc

@router.post("/cases/{case_id}/reactivate",response_model=CasePublic)
def reactivate_case(case_id:uuid.UUID,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return CasePublic.model_validate(PostpartumService(session).set_active(case_id,True,user.id))
    except Exception as exc:raise error(exc) from exc

@router.post("/cases/{case_id}/room-changes",response_model=RoomHistoryPublic,status_code=201)
def change_room(case_id:uuid.UUID,data:RoomChangeCreate,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return RoomHistoryPublic.model_validate(PostpartumService(session).change_room(case_id,data,user.id))
    except Exception as exc:raise error(exc) from exc

@router.post("/cases/{case_id}/pauses",response_model=PausePublic,status_code=201)
def create_pause(case_id:uuid.UUID,data:PauseCreate,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return PausePublic.model_validate(PostpartumService(session).create_pause(case_id,data,user.id))
    except Exception as exc:raise error(exc) from exc

@router.patch("/cases/{case_id}/pauses/{pause_id}",response_model=PausePublic)
def update_pause(case_id:uuid.UUID,pause_id:uuid.UUID,data:PauseUpdate,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return PausePublic.model_validate(PostpartumService(session).update_pause(case_id,pause_id,data,user.id))
    except Exception as exc:raise error(exc) from exc

@router.delete("/cases/{case_id}/pauses/{pause_id}",status_code=204)
def delete_pause(case_id:uuid.UUID,pause_id:uuid.UUID,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:PostpartumService(session).delete_pause(case_id,pause_id,user.id)
    except Exception as exc:raise error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
