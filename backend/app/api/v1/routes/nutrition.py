import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.domains.auth.dependencies import get_current_user, require_admin
from app.domains.auth.exceptions import InvalidCredentialsError
from app.domains.nutrition.exceptions import InvalidNutritionSourceError, NutritionFoodInUseError, NutritionFoodNotFoundError, NutritionImportError
from app.domains.nutrition.models import NutritionNutrient
from app.domains.nutrition.schemas import FoodDetail, FoodList, FoodSummary, ImportBatchPublic, ImportList, ImportPreview, ManualFoodCreate, ManualFoodUpdate, NutrientPublic
from app.domains.nutrition.service import NutritionService
from app.domains.users.models import User
from app.shared.schemas import PaginationMeta, PasswordConfirmation

router=APIRouter(prefix="/nutrition",tags=["nutrition"],dependencies=[Depends(get_current_user)])


def mapped(exc:Exception):
    if isinstance(exc,NutritionFoodNotFoundError):return HTTPException(404,"Nutrition food not found")
    if isinstance(exc,NutritionImportError):return HTTPException(422,str(exc))
    if isinstance(exc,InvalidNutritionSourceError):return HTTPException(422,str(exc))
    if isinstance(exc,NutritionFoodInUseError):return HTTPException(409,"Nutrition food is mapped to an ingredient")
    if isinstance(exc,InvalidCredentialsError):return HTTPException(401,"Password verification failed")
    return HTTPException(400,"Nutrition operation failed")


@router.get("/foods",response_model=FoodList)
def foods(session:Annotated[Session,Depends(get_db_session)],source:Literal["tfda","manual"]|None=None,page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),search:str|None=None,category:str|None=None,active:bool|None=None):
    items,total=NutritionService(session).list(source=source,page=page,page_size=page_size,search=search,category=category,active=active)
    return FoodList(items=[FoodSummary.model_validate(item) for item in items],pagination=PaginationMeta(page=page,page_size=page_size,total=total))


@router.get("/foods/categories",response_model=list[str])
def categories(session:Annotated[Session,Depends(get_db_session)],source:Literal["tfda","manual"]="tfda"):return NutritionService(session).categories(source)


@router.get("/foods/{food_id}",response_model=FoodDetail)
def detail(food_id:uuid.UUID,session:Annotated[Session,Depends(get_db_session)]):
    try:return FoodDetail.model_validate(NutritionService(session).get(food_id))
    except Exception as exc:raise mapped(exc) from exc


@router.get("/nutrients",response_model=list[NutrientPublic])
def nutrients(session:Annotated[Session,Depends(get_db_session)]):return list(session.scalars(select(NutritionNutrient).order_by(NutritionNutrient.sort_order)))


@router.get("/manual-foods",response_model=FoodList)
def manual_foods(session:Annotated[Session,Depends(get_db_session)],page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),search:str|None=None,active:bool|None=None):
    items,total=NutritionService(session).list(source="manual",page=page,page_size=page_size,search=search,category=None,active=active)
    return FoodList(items=[FoodSummary.model_validate(item) for item in items],pagination=PaginationMeta(page=page,page_size=page_size,total=total))


@router.post("/manual-foods",response_model=FoodDetail,status_code=201)
def create_manual(data:ManualFoodCreate,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return FoodDetail.model_validate(NutritionService(session).create_manual(data,user.id))
    except Exception as exc:raise mapped(exc) from exc


@router.patch("/manual-foods/{food_id}",response_model=FoodDetail)
def update_manual(food_id:uuid.UUID,data:ManualFoodUpdate,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return FoodDetail.model_validate(NutritionService(session).update_manual(food_id,data,user.id))
    except Exception as exc:raise mapped(exc) from exc


@router.post("/manual-foods/{food_id}/deactivate",response_model=FoodDetail)
def deactivate_manual(food_id:uuid.UUID,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return FoodDetail.model_validate(NutritionService(session).set_manual_active(food_id,False,user.id))
    except Exception as exc:raise mapped(exc) from exc


@router.post("/manual-foods/{food_id}/reactivate",response_model=FoodDetail)
def reactivate_manual(food_id:uuid.UUID,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return FoodDetail.model_validate(NutritionService(session).set_manual_active(food_id,True,user.id))
    except Exception as exc:raise mapped(exc) from exc


@router.post("/manual-foods/{food_id}/hard-delete",status_code=204)
def hard_delete(food_id:uuid.UUID,data:PasswordConfirmation,user:Annotated[User,Depends(require_admin)],session:Annotated[Session,Depends(get_db_session)]):
    try:NutritionService(session).hard_delete_manual(food_id,user.id,data.password)
    except Exception as exc:raise mapped(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/imports/preview",response_model=ImportPreview)
async def preview(file:Annotated[UploadFile,File()],user:Annotated[User,Depends(require_admin)],session:Annotated[Session,Depends(get_db_session)]):
    try:return ImportPreview.model_validate(NutritionService(session).preview(await file.read(),file.filename or "upload.xlsx"))
    except Exception as exc:raise mapped(exc) from exc


@router.post("/imports/confirm",response_model=ImportBatchPublic,status_code=201)
async def confirm(file:Annotated[UploadFile,File()],user:Annotated[User,Depends(require_admin)],session:Annotated[Session,Depends(get_db_session)],version_label:Annotated[str|None,Form()]=None):
    try:return ImportBatchPublic.model_validate(NutritionService(session).confirm(await file.read(),file.filename or "upload.xlsx",version_label,user.id))
    except Exception as exc:raise mapped(exc) from exc


@router.get("/imports",response_model=ImportList)
def imports(session:Annotated[Session,Depends(get_db_session)],page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100)):
    items,total=NutritionService(session).imports(page,page_size)
    return ImportList(items=[ImportBatchPublic.model_validate(item) for item in items],pagination=PaginationMeta(page=page,page_size=page_size,total=total))
