import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter,Depends,File,HTTPException,Query,Response,UploadFile,status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.domains.auth.dependencies import get_current_user,require_admin
from app.domains.production.exceptions import ProductionConflict,ProductionError,ProductionImageError,ProductionIngredientNotFound,ProductionMenuNotFound,ProductionProfileNotFound,ProductionStepNotFound,ProductionValidationError,ProductionVersionNotFound
from app.domains.production.schemas import IngredientUpdate,MenuProductionPlan,ProfileCreate,ProfilePublic,ProfileUpdate,StepCreate,StepReorder,StepUpdate,VersionCopy,VersionCreate,VersionUpdate
from app.domains.production.service import MAX_IMAGE_BYTES,ProductionService
from app.domains.users.models import User

dish_router=APIRouter(prefix="/dishes/{dish_id}/production-profile",tags=["production"],dependencies=[Depends(get_current_user)])
menu_router=APIRouter(prefix="/menus/{menu_id}/production-plan",tags=["production"],dependencies=[Depends(get_current_user)])

def mapped(exc:Exception):
    if isinstance(exc,(ProductionProfileNotFound,ProductionVersionNotFound,ProductionStepNotFound,ProductionIngredientNotFound,ProductionMenuNotFound)):return HTTPException(404,"Production resource not found")
    if isinstance(exc,ProductionConflict):return HTTPException(409,"Production profile or batch version already exists")
    if isinstance(exc,(ProductionValidationError,ProductionImageError)):return HTTPException(422,str(exc) or "Production data is invalid")
    raise exc

@dish_router.get("",response_model=ProfilePublic)
def get_profile(dish_id:uuid.UUID,session:Annotated[Session,Depends(get_db_session)]):
    try:return ProfilePublic.model_validate(ProductionService(session).get_profile(dish_id))
    except Exception as exc:raise mapped(exc) from exc
@dish_router.post("",response_model=ProfilePublic,status_code=201)
def create_profile(dish_id:uuid.UUID,data:ProfileCreate,user:Annotated[User,Depends(require_admin)],session:Annotated[Session,Depends(get_db_session)]):
    try:return ProfilePublic.model_validate(ProductionService(session).create_profile(dish_id,data,user.id))
    except Exception as exc:raise mapped(exc) from exc
@dish_router.patch("",response_model=ProfilePublic)
def update_profile(dish_id:uuid.UUID,data:ProfileUpdate,user:Annotated[User,Depends(require_admin)],session:Annotated[Session,Depends(get_db_session)]):
    try:return ProfilePublic.model_validate(ProductionService(session).update_profile(dish_id,data,user.id))
    except Exception as exc:raise mapped(exc) from exc
@dish_router.delete("",status_code=204)
def delete_profile(dish_id:uuid.UUID,user:Annotated[User,Depends(require_admin)],session:Annotated[Session,Depends(get_db_session)]):
    try:ProductionService(session).delete_profile(dish_id,user.id);return Response(status_code=204)
    except Exception as exc:raise mapped(exc) from exc
@dish_router.get("/preview")
def preview(dish_id:uuid.UUID,servings:int,session:Annotated[Session,Depends(get_db_session)]):
    if servings<=0:raise HTTPException(422,"Servings must be positive")
    try:return ProductionService(session).dish_plan(dish_id,servings)
    except Exception as exc:raise mapped(exc) from exc
@dish_router.post("/versions",response_model=ProfilePublic,status_code=201)
def create_version(dish_id:uuid.UUID,data:VersionCreate,user:Annotated[User,Depends(require_admin)],session:Annotated[Session,Depends(get_db_session)]):
    try:return ProfilePublic.model_validate(ProductionService(session).create_version(dish_id,data,user.id))
    except Exception as exc:raise mapped(exc) from exc
@dish_router.post("/versions/{version_id}/copy",response_model=ProfilePublic,status_code=201)
def copy_version(dish_id:uuid.UUID,version_id:uuid.UUID,data:VersionCopy,user:Annotated[User,Depends(require_admin)],session:Annotated[Session,Depends(get_db_session)]):
    try:return ProfilePublic.model_validate(ProductionService(session).copy_version(dish_id,version_id,data,user.id))
    except Exception as exc:raise mapped(exc) from exc
@dish_router.patch("/versions/{version_id}",response_model=ProfilePublic)
def update_version(dish_id:uuid.UUID,version_id:uuid.UUID,data:VersionUpdate,user:Annotated[User,Depends(require_admin)],session:Annotated[Session,Depends(get_db_session)]):
    try:return ProfilePublic.model_validate(ProductionService(session).update_version(dish_id,version_id,data,user.id))
    except Exception as exc:raise mapped(exc) from exc
@dish_router.delete("/versions/{version_id}",response_model=ProfilePublic)
def delete_version(dish_id:uuid.UUID,version_id:uuid.UUID,user:Annotated[User,Depends(require_admin)],session:Annotated[Session,Depends(get_db_session)]):
    try:return ProfilePublic.model_validate(ProductionService(session).delete_version(dish_id,version_id,user.id))
    except Exception as exc:raise mapped(exc) from exc
@dish_router.patch("/versions/{version_id}/ingredients/{item_id}",response_model=ProfilePublic)
def update_ingredient(dish_id:uuid.UUID,version_id:uuid.UUID,item_id:uuid.UUID,data:IngredientUpdate,user:Annotated[User,Depends(require_admin)],session:Annotated[Session,Depends(get_db_session)]):
    try:return ProfilePublic.model_validate(ProductionService(session).update_ingredient(dish_id,version_id,item_id,data,user.id))
    except Exception as exc:raise mapped(exc) from exc
@dish_router.post("/versions/{version_id}/steps",response_model=ProfilePublic,status_code=201)
def create_step(dish_id:uuid.UUID,version_id:uuid.UUID,data:StepCreate,user:Annotated[User,Depends(require_admin)],session:Annotated[Session,Depends(get_db_session)]):
    try:return ProfilePublic.model_validate(ProductionService(session).create_step(dish_id,version_id,data,user.id))
    except Exception as exc:raise mapped(exc) from exc
@dish_router.patch("/versions/{version_id}/steps/{step_id}",response_model=ProfilePublic)
def update_step(dish_id:uuid.UUID,version_id:uuid.UUID,step_id:uuid.UUID,data:StepUpdate,user:Annotated[User,Depends(require_admin)],session:Annotated[Session,Depends(get_db_session)]):
    try:return ProfilePublic.model_validate(ProductionService(session).update_step(dish_id,version_id,step_id,data,user.id))
    except Exception as exc:raise mapped(exc) from exc
@dish_router.delete("/versions/{version_id}/steps/{step_id}",response_model=ProfilePublic)
def delete_step(dish_id:uuid.UUID,version_id:uuid.UUID,step_id:uuid.UUID,user:Annotated[User,Depends(require_admin)],session:Annotated[Session,Depends(get_db_session)]):
    try:return ProfilePublic.model_validate(ProductionService(session).delete_step(dish_id,version_id,step_id,user.id))
    except Exception as exc:raise mapped(exc) from exc
@dish_router.put("/versions/{version_id}/steps/reorder",response_model=ProfilePublic)
def reorder_steps(dish_id:uuid.UUID,version_id:uuid.UUID,data:StepReorder,user:Annotated[User,Depends(require_admin)],session:Annotated[Session,Depends(get_db_session)]):
    try:return ProfilePublic.model_validate(ProductionService(session).reorder_steps(dish_id,version_id,data.ordered_ids,user.id))
    except Exception as exc:raise mapped(exc) from exc
@dish_router.post("/image",response_model=ProfilePublic)
async def upload_image(dish_id:uuid.UUID,user:Annotated[User,Depends(require_admin)],session:Annotated[Session,Depends(get_db_session)],file:UploadFile=File(...)):
    payload=await file.read(MAX_IMAGE_BYTES+1)
    try:return ProfilePublic.model_validate(ProductionService(session).save_image(dish_id,payload,file.content_type or "",user.id))
    except Exception as exc:raise mapped(exc) from exc
@dish_router.get("/image")
def get_image(dish_id:uuid.UUID,session:Annotated[Session,Depends(get_db_session)]):
    try:path,mime=ProductionService(session).image(dish_id);return FileResponse(path,media_type=mime,headers={"X-Content-Type-Options":"nosniff","Cache-Control":"private, max-age=300"})
    except Exception as exc:raise mapped(exc) from exc
@dish_router.delete("/image",response_model=ProfilePublic)
def delete_image(dish_id:uuid.UUID,user:Annotated[User,Depends(require_admin)],session:Annotated[Session,Depends(get_db_session)]):
    try:return ProfilePublic.model_validate(ProductionService(session).delete_image(dish_id,user.id))
    except Exception as exc:raise mapped(exc) from exc

@menu_router.get("",response_model=MenuProductionPlan)
def menu_plan(menu_id:uuid.UUID,session:Annotated[Session,Depends(get_db_session)],date_value:date|None=Query(None,alias="date"),meal_type_id:uuid.UUID|None=None):
    try:return MenuProductionPlan.model_validate(ProductionService(session).menu_plan(menu_id,date_value,meal_type_id))
    except Exception as exc:raise mapped(exc) from exc
