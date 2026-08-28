from typing import Annotated
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.domains.auth.dependencies import get_current_user
from app.domains.requirements.exceptions import RequirementMenuNotFoundError
from app.domains.requirements.schemas import RequirementCriteria,RequirementResult
from app.domains.requirements.service import RequirementService

router=APIRouter(prefix="/requirements",tags=["requirements"],dependencies=[Depends(get_current_user)])


@router.post("/calculate",response_model=RequirementResult)
def calculate(criteria:RequirementCriteria,session:Annotated[Session,Depends(get_db_session)]):
    try:return RequirementResult.model_validate(RequirementService(session).calculate(criteria))
    except RequirementMenuNotFoundError as exc:raise HTTPException(404,"One or more menus were not found") from exc
    except Exception as exc:raise HTTPException(400,"Requirement calculation failed") from exc
