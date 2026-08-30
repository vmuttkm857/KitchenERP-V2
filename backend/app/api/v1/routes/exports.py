import uuid
from typing import Annotated,Literal
from fastapi import APIRouter,Depends,HTTPException,Response
from sqlalchemy.orm import Session
from app.api.dependencies import get_db_session
from app.domains.auth.dependencies import get_current_user
from app.domains.exports.exceptions import EmptyExportError
from app.domains.exports.safety import content_disposition,safe_filename
from app.domains.exports.service import ExportService
from app.domains.kitchen_operations.exceptions import KitchenMenuNotFoundError
from app.domains.kitchen_operations.schemas import KitchenCriteria
from app.domains.purchases.exceptions import PurchaseNotFoundError
from app.domains.requirements.exceptions import RequirementMenuNotFoundError
from app.domains.requirements.schemas import RequirementCriteria
from app.domains.snapshots.exceptions import SnapshotNotFoundError
router=APIRouter(prefix="/exports",tags=["exports"],dependencies=[Depends(get_current_user)])
TYPES={"xlsx":"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet","pdf":"application/pdf"}
def binary(payload,name,format):
    filename=safe_filename(name,format);return Response(payload,media_type=TYPES[format],headers={"Content-Disposition":content_disposition(filename),"X-Content-Type-Options":"nosniff"})
def mapped(exc):
    if isinstance(exc,(KitchenMenuNotFoundError,RequirementMenuNotFoundError,SnapshotNotFoundError,PurchaseNotFoundError)):return HTTPException(404,"Export source not found")
    if isinstance(exc,EmptyExportError):return HTTPException(422,detail={"code":"EMPTY_EXPORT","message":str(exc)})
    return HTTPException(400,detail={"code":"EXPORT_FAILED","message":"The export could not be generated"})
@router.post("/kitchen-operations/a4-xlsx")
def export_kitchen_a4(criteria:KitchenCriteria,session:Annotated[Session,Depends(get_db_session)]):
    try:payload,name=ExportService(session).kitchen_a4(criteria);return binary(payload,f"{name}_A4廚房作業表","xlsx")
    except Exception as exc:raise mapped(exc) from exc
@router.post("/kitchen-operations/{format}")
def export_kitchen(format:Literal["xlsx","pdf"],criteria:KitchenCriteria,session:Annotated[Session,Depends(get_db_session)]):
    try:payload,name=ExportService(session).kitchen(criteria,format);return binary(payload,f"{name}_廚房備料",format)
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
