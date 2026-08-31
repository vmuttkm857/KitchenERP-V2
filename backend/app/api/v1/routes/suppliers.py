import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.domains.auth.dependencies import get_current_user, require_admin
from app.domains.auth.exceptions import InvalidCredentialsError
from app.domains.suppliers.exceptions import InvalidSupplierOrderError, SupplierCodeExistsError, SupplierInUseError, SupplierNotFoundError
from app.domains.suppliers.schemas import SupplierCreate, SupplierList, SupplierPublic, SupplierReorder, SupplierUpdate
from app.domains.suppliers.service import SupplierService
from app.domains.users.models import User
from app.shared.schemas import PaginationMeta, PasswordConfirmation


router = APIRouter(prefix="/suppliers", tags=["suppliers"], dependencies=[Depends(get_current_user)])


def map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SupplierNotFoundError): return HTTPException(404, "Supplier not found")
    if isinstance(exc, SupplierCodeExistsError): return HTTPException(409, "Supplier code already exists")
    if isinstance(exc, SupplierInUseError): return HTTPException(409, "Supplier is referenced and cannot be permanently deleted")
    if isinstance(exc, InvalidSupplierOrderError): return HTTPException(422, str(exc))
    if isinstance(exc, InvalidCredentialsError): return HTTPException(401, "Password verification failed")
    return HTTPException(400, "Supplier operation failed")


@router.get("", response_model=SupplierList)
def list_suppliers(session: Annotated[Session, Depends(get_db_session)], page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), active: bool | None = None, search: str | None = None) -> SupplierList:
    items, total = SupplierService(session).list(page, page_size, active, search)
    return SupplierList(items=[SupplierPublic.model_validate(item) for item in items], pagination=PaginationMeta(page=page, page_size=page_size, total=total))


@router.get("/order", response_model=list[uuid.UUID])
def supplier_order(session: Annotated[Session, Depends(get_db_session)]) -> list[uuid.UUID]:
    return SupplierService(session).ordered_ids()


@router.post("/reorder", status_code=204)
def reorder_suppliers(data: SupplierReorder, user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]) -> Response:
    try: SupplierService(session).reorder(data.supplier_ids, user.id)
    except Exception as exc: raise map_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{supplier_id}", response_model=SupplierPublic)
def get_supplier(supplier_id: uuid.UUID, session: Annotated[Session, Depends(get_db_session)]) -> SupplierPublic:
    try: return SupplierPublic.model_validate(SupplierService(session).get(supplier_id))
    except Exception as exc: raise map_error(exc) from exc


@router.post("", response_model=SupplierPublic, status_code=201)
def create_supplier(data: SupplierCreate, user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]) -> SupplierPublic:
    try: return SupplierPublic.model_validate(SupplierService(session).create(data, user.id))
    except Exception as exc: raise map_error(exc) from exc


@router.patch("/{supplier_id}", response_model=SupplierPublic)
def update_supplier(supplier_id: uuid.UUID, data: SupplierUpdate, user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]) -> SupplierPublic:
    try: return SupplierPublic.model_validate(SupplierService(session).update(supplier_id, data, user.id))
    except Exception as exc: raise map_error(exc) from exc


@router.post("/{supplier_id}/deactivate", response_model=SupplierPublic)
def deactivate_supplier(supplier_id: uuid.UUID, user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]) -> SupplierPublic:
    try: return SupplierPublic.model_validate(SupplierService(session).set_active(supplier_id, False, user.id))
    except Exception as exc: raise map_error(exc) from exc


@router.post("/{supplier_id}/reactivate", response_model=SupplierPublic)
def reactivate_supplier(supplier_id: uuid.UUID, user: Annotated[User, Depends(get_current_user)], session: Annotated[Session, Depends(get_db_session)]) -> SupplierPublic:
    try: return SupplierPublic.model_validate(SupplierService(session).set_active(supplier_id, True, user.id))
    except Exception as exc: raise map_error(exc) from exc


@router.post("/{supplier_id}/hard-delete", status_code=204)
def hard_delete_supplier(supplier_id: uuid.UUID, confirmation: PasswordConfirmation, user: Annotated[User, Depends(require_admin)], session: Annotated[Session, Depends(get_db_session)]) -> Response:
    try: SupplierService(session).hard_delete(supplier_id, user.id, confirmation.password)
    except Exception as exc: raise map_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
