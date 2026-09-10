import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session
from app.api.dependencies import get_db_session
from app.domains.auth.dependencies import get_current_user
from app.domains.postpartum.exceptions import (
    InvalidPostpartumDataError, InvalidPostpartumMenuSourceError, InvalidPostpartumRestrictionAssociationError,
    PostpartumCaseNotFoundError, PostpartumPauseNotFoundError,
    PostpartumRestrictionGroupNameExistsError, PostpartumRestrictionGroupNotFoundError,
    PostpartumMenuSourceNotFoundError,
)
from app.domains.postpartum.schemas import (
    CaseCreate, CaseDetail, CaseList, CaseListItem, CasePublic, CaseRestrictionGroupsPublic,
    CaseRestrictionGroupsReplace, CaseStatus, CaseUpdate, PauseCreate, PausePublic,
    PauseUpdate, RestrictionAssociationsReplace, RestrictionGroupCreate, RestrictionGroupDetail,
    RestrictionGroupList, RestrictionGroupPublic, RestrictionGroupUpdate, RoomChangeCreate, RoomHistoryPublic,
    MenuSourceList, MenuSourcePublic, MenuSourceReplace,
)
from app.domains.postpartum.service import PostpartumService
from app.domains.users.models import User
from app.shared.schemas import PaginationMeta

router = APIRouter(prefix="/postpartum", tags=["postpartum"], dependencies=[Depends(get_current_user)])

def error(exc):
    if isinstance(exc, (PostpartumCaseNotFoundError, PostpartumPauseNotFoundError, PostpartumRestrictionGroupNotFoundError, PostpartumMenuSourceNotFoundError)): return HTTPException(404, "Postpartum resource not found")
    if isinstance(exc, PostpartumRestrictionGroupNameExistsError): return HTTPException(409, "禁忌群組名稱已存在")
    if isinstance(exc, (InvalidPostpartumDataError, InvalidPostpartumMenuSourceError, InvalidPostpartumRestrictionAssociationError)): return HTTPException(422, str(exc))
    return HTTPException(400, "Postpartum operation failed")


@router.get("/menu-sources", response_model=MenuSourceList)
def menu_sources(session: Annotated[Session, Depends(get_db_session)],
                 from_date: date | None = None, to_date: date | None = None):
    try: return MenuSourceList(items=[
        MenuSourcePublic.model_validate(item)
        for item in PostpartumService(session).menu_sources(from_date, to_date)
    ])
    except Exception as exc: raise error(exc) from exc


@router.post("/menu-sources", response_model=MenuSourcePublic, status_code=201)
def create_menu_source(data: MenuSourceReplace, user: Annotated[User, Depends(get_current_user)],
                       session: Annotated[Session, Depends(get_db_session)]):
    try: return MenuSourcePublic.model_validate(PostpartumService(session).create_menu_source(data, user.id))
    except Exception as exc: raise error(exc) from exc


@router.get("/menu-sources/{source_id}", response_model=MenuSourcePublic)
def menu_source(source_id: uuid.UUID, session: Annotated[Session, Depends(get_db_session)]):
    try: return MenuSourcePublic.model_validate(PostpartumService(session).menu_source(source_id))
    except Exception as exc: raise error(exc) from exc


@router.put("/menu-sources/{source_id}", response_model=MenuSourcePublic)
def update_menu_source(source_id: uuid.UUID, data: MenuSourceReplace,
                       user: Annotated[User, Depends(get_current_user)],
                       session: Annotated[Session, Depends(get_db_session)]):
    try: return MenuSourcePublic.model_validate(PostpartumService(session).update_menu_source(source_id, data, user.id))
    except Exception as exc: raise error(exc) from exc

@router.get("/cases", response_model=CaseList)
def cases(session: Annotated[Session, Depends(get_db_session)], page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), active: bool | None = None, status_filter: CaseStatus | None = Query(default=None, alias="status"), search: str | None = None):
    try:
        items,total=PostpartumService(session).list(page,page_size,active,status_filter,search)
        return CaseList(items=[CaseListItem(
            **CasePublic.model_validate(item["case"]).model_dump(),
            restriction_groups=item["restriction_groups"],
        ) for item in items],pagination=PaginationMeta(page=page,page_size=page_size,total=total))
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


@router.put("/cases/{case_id}/restriction-groups", response_model=CaseRestrictionGroupsPublic)
def replace_case_restriction_groups(case_id: uuid.UUID, data: CaseRestrictionGroupsReplace,
    user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]):
    try:
        return CaseRestrictionGroupsPublic.model_validate(
            PostpartumService(session).replace_case_restriction_groups(case_id, data, user.id)
        )
    except Exception as exc:
        raise error(exc) from exc


@router.get("/restriction-groups", response_model=RestrictionGroupList)
def restriction_groups(session: Annotated[Session, Depends(get_db_session)], page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), active: bool | None = None, search: str | None = None):
    items, total = PostpartumService(session).list_restriction_groups(page, page_size, active, search)
    return RestrictionGroupList(items=[RestrictionGroupPublic.model_validate(item) for item in items], pagination=PaginationMeta(page=page, page_size=page_size, total=total))


@router.post("/restriction-groups", response_model=RestrictionGroupPublic, status_code=201)
def create_restriction_group(data: RestrictionGroupCreate, user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]):
    try: return RestrictionGroupPublic.model_validate(PostpartumService(session).create_restriction_group(data, user.id))
    except Exception as exc: raise error(exc) from exc


@router.get("/restriction-groups/{group_id}", response_model=RestrictionGroupDetail)
def restriction_group_detail(group_id: uuid.UUID, session: Annotated[Session, Depends(get_db_session)]):
    try: return RestrictionGroupDetail.model_validate(PostpartumService(session).restriction_group_detail(group_id))
    except Exception as exc: raise error(exc) from exc


@router.patch("/restriction-groups/{group_id}", response_model=RestrictionGroupPublic)
def update_restriction_group(group_id: uuid.UUID, data: RestrictionGroupUpdate, user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]):
    try: return RestrictionGroupPublic.model_validate(PostpartumService(session).update_restriction_group(group_id, data, user.id))
    except Exception as exc: raise error(exc) from exc


@router.post("/restriction-groups/{group_id}/deactivate", response_model=RestrictionGroupPublic)
def deactivate_restriction_group(group_id: uuid.UUID, user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]):
    try: return RestrictionGroupPublic.model_validate(PostpartumService(session).set_restriction_group_active(group_id, False, user.id))
    except Exception as exc: raise error(exc) from exc


@router.post("/restriction-groups/{group_id}/reactivate", response_model=RestrictionGroupPublic)
def reactivate_restriction_group(group_id: uuid.UUID, user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]):
    try: return RestrictionGroupPublic.model_validate(PostpartumService(session).set_restriction_group_active(group_id, True, user.id))
    except Exception as exc: raise error(exc) from exc


@router.put("/restriction-groups/{group_id}/associations", response_model=RestrictionGroupDetail)
def replace_restriction_associations(group_id: uuid.UUID, data: RestrictionAssociationsReplace, user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]):
    try: return RestrictionGroupDetail.model_validate(PostpartumService(session).replace_restriction_associations(group_id, data, user.id))
    except Exception as exc: raise error(exc) from exc
