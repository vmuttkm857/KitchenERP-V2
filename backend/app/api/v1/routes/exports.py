import uuid
from datetime import date
from typing import Annotated,Literal
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from sqlalchemy.orm import Session
from app.api.dependencies import get_db_session
from app.domains.auth.dependencies import get_current_user
from app.domains.exports.exceptions import EmptyExportError
from app.domains.exports.safety import content_disposition,safe_filename
from app.domains.exports.service import ExportService
from app.domains.kitchen_operations.exceptions import KitchenMenuNotFoundError
from app.domains.kitchen_operations.schemas import KitchenCriteria
from app.domains.menus.exceptions import MenuNotFoundError
from app.domains.purchases.exceptions import PurchaseNotFoundError
from app.domains.production.exceptions import ProductionMenuNotFound,ProductionValidationError
from app.domains.requirements.exceptions import RequirementMenuNotFoundError
from app.domains.requirements.schemas import RequirementCriteria
from app.domains.snapshots.exceptions import SnapshotNotFoundError
router=APIRouter(prefix="/exports",tags=["exports"],dependencies=[Depends(get_current_user)])
TYPES={"xlsx":"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet","pdf":"application/pdf"}
def binary(payload,name,format):
    filename=safe_filename(name,format);return Response(payload,media_type=TYPES[format],headers={"Content-Disposition":content_disposition(filename),"X-Content-Type-Options":"nosniff"})
def mapped(exc):
    if isinstance(exc,(KitchenMenuNotFoundError,MenuNotFoundError,RequirementMenuNotFoundError,SnapshotNotFoundError,PurchaseNotFoundError,ProductionMenuNotFound)):return HTTPException(404,"Export source not found")
    if isinstance(exc,ProductionValidationError):return HTTPException(422,detail={"code":"INVALID_PRODUCTION_SCOPE","message":str(exc)})
    if isinstance(exc,EmptyExportError):return HTTPException(422,detail={"code":"EMPTY_EXPORT","message":str(exc)})
    return HTTPException(400,detail={"code":"EXPORT_FAILED","message":"The export could not be generated"})
@router.post("/kitchen-operations/a4-xlsx")
def export_kitchen_a4(criteria:KitchenCriteria,session:Annotated[Session,Depends(get_db_session)]):
    try:payload,name=ExportService(session).kitchen_a4(criteria);return binary(payload,f"{name}_A4廚房作業表","xlsx")
    except Exception as exc:raise mapped(exc) from exc
@router.post("/kitchen-operations/simple/{format}")
def export_kitchen_simple(format:Literal["xlsx","pdf"],criteria:KitchenCriteria,session:Annotated[Session,Depends(get_db_session)],variant:Literal["single","poster"]="single"):
    if variant=="poster" and format!="xlsx":raise HTTPException(422,detail={"code":"INVALID_EXPORT_VARIANT","message":"Poster export is Excel only"})
    try:payload,name=ExportService(session).kitchen_simple(criteria,format,variant);return binary(payload,f"{name}_週配料表",format)
    except Exception as exc:raise mapped(exc) from exc
@router.post("/kitchen-operations/{format}")
def export_kitchen(format:Literal["xlsx","pdf"],criteria:KitchenCriteria,session:Annotated[Session,Depends(get_db_session)]):
    try:payload,name=ExportService(session).kitchen(criteria,format);return binary(payload,f"{name}_廚房備料",format)
    except Exception as exc:raise mapped(exc) from exc
@router.get("/menus/{menu_id}/recipe-cards/pdf")
def export_recipe_cards(menu_id:uuid.UUID,session:Annotated[Session,Depends(get_db_session)],date_value:date|None=Query(None,alias="date"),meal_type_id:uuid.UUID|None=None,mode:Literal["work","detailed"]="work"):
    try:payload,name=ExportService(session).recipe_cards(menu_id,date_value,meal_type_id,mode);return binary(payload,name,"pdf")
    except Exception as exc:raise mapped(exc) from exc
@router.get("/menus/{menu_id}/{layout}/{format}")
def export_menu(menu_id:uuid.UUID,layout:Literal["full","merged","grid","pretty"],format:Literal["xlsx","pdf"],session:Annotated[Session,Depends(get_db_session)],variant:Literal["single","poster"]="single",nutrition:Literal["none","calories","detailed"]="none"):
    if variant=="poster" and (format!="xlsx" or layout=="pretty"):raise HTTPException(422,detail={"code":"INVALID_EXPORT_VARIANT","message":"Poster export is available for merged/grid Excel only"})
    if variant=="poster" and nutrition=="detailed":raise HTTPException(422,detail={"code":"INVALID_NUTRITION_VARIANT","message":"Detailed nutrition is not available for poster exports"})
    try:
        payload,name=ExportService(session).menu(menu_id,layout,format,variant,nutrition)
        label={"full":"餐別合併週表","merged":"餐別合併週表","grid":"菜色分格週表","pretty":"漂亮公告版"}[layout]
        suffix={"none":"","calories":"_含熱量","detailed":"_營養詳細"}[nutrition]
        return binary(payload,f"{name}_{label}{suffix}",format)
    except Exception as exc:raise mapped(exc) from exc
@router.post("/requirements/xlsx")
def export_requirements(criteria:RequirementCriteria,session:Annotated[Session,Depends(get_db_session)]):
    try:payload,name=ExportService(session).requirements(criteria);return binary(payload,name,"xlsx")
    except Exception as exc:raise mapped(exc) from exc
@router.get("/requirement-snapshots/{snapshot_id}/xlsx")
def export_snapshot(snapshot_id:uuid.UUID,session:Annotated[Session,Depends(get_db_session)]):
    try:payload,name=ExportService(session).snapshot(snapshot_id);return binary(payload,name,"xlsx")
    except Exception as exc:raise mapped(exc) from exc
@router.get("/purchases/{purchase_id}/{format}")
def export_purchase(purchase_id:uuid.UUID,format:Literal["xlsx","pdf"],session:Annotated[Session,Depends(get_db_session)]):
    try:payload,name=ExportService(session).purchase(purchase_id,format);return binary(payload,name,format)
    except Exception as exc:raise mapped(exc) from exc
