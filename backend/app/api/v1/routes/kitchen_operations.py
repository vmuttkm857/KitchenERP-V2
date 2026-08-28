from typing import Annotated
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from app.api.dependencies import get_db_session
from app.domains.auth.dependencies import get_current_user
from app.domains.kitchen_operations.exceptions import KitchenMenuNotFoundError
from app.domains.kitchen_operations.schemas import KitchenCriteria,KitchenResult
from app.domains.kitchen_operations.service import KitchenOperationsService
router=APIRouter(prefix="/kitchen-operations",tags=["kitchen-operations"],dependencies=[Depends(get_current_user)])
@router.post("/calculate",response_model=KitchenResult)
def calculate(criteria:KitchenCriteria,session:Annotated[Session,Depends(get_db_session)]):
    try:return KitchenResult.model_validate(KitchenOperationsService(session).calculate(criteria))
    except KitchenMenuNotFoundError as exc:raise HTTPException(404,"Menu not found") from exc
    except Exception as exc:raise HTTPException(400,"Kitchen operation calculation failed") from exc
