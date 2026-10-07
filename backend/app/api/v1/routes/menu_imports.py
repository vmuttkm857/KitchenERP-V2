import logging
from typing import Annotated

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.domains.auth.dependencies import get_current_user
from app.domains.menu_imports.exceptions import (
    MenuImportAlreadyFinalizedError,
    MenuImportDishUnavailableError,
    MenuImportDuplicateError,
    MenuImportFatalError,
    MenuImportHashMismatchError,
    MenuImportLineNotFoundError,
    MenuImportNotFoundError,
    MenuImportNotReadyError,
    MenuImportValidationError,
)
from app.domains.menu_imports.parser import MAX_FILE_SIZE
from app.domains.menu_imports.schemas import (
    MenuImportBatchDetail,
    MenuImportBatchList,
    MenuImportBatchSummary,
    MenuImportFinalize,
    MenuImportFinalizeResponse,
    MenuImportLineResolve,
    MenuImportPreview,
)
from app.domains.menu_imports.service import MenuImportService
from app.domains.users.models import User
from app.shared.schemas import PaginationMeta

router = APIRouter(prefix="/menu-imports", tags=["menu-imports"], dependencies=[Depends(get_current_user)])
logger = logging.getLogger("kitchenerp.menu_imports")


def mapped_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MenuImportNotFoundError):
        return HTTPException(404, "Menu import draft not found")
    if isinstance(exc, MenuImportLineNotFoundError):
        return HTTPException(404, "Menu import line not found")
    if isinstance(exc, MenuImportHashMismatchError):
        return HTTPException(409, {"code": "SOURCE_HASH_MISMATCH"})
    if isinstance(exc, MenuImportFatalError):
        return HTTPException(422, {"code": "MENU_IMPORT_FATAL", "errors": exc.errors})
    if isinstance(exc, MenuImportDuplicateError):
        return HTTPException(409, {
            "code": "MENU_IMPORT_DRAFT_EXISTS", "existing_batch_id": str(exc.batch_id),
        })
    if isinstance(exc, MenuImportDishUnavailableError):
        return HTTPException(422, {"code": "DISH_NOT_ACTIVE_OR_NOT_FOUND"})
    if isinstance(exc, MenuImportAlreadyFinalizedError):
        return HTTPException(409, {
            "code": "MENU_IMPORT_ALREADY_FINALIZED",
            "finalized_menu_id": str(exc.menu_id) if exc.menu_id else None,
        })
    if isinstance(exc, MenuImportNotReadyError):
        return HTTPException(409, {"code": "MENU_IMPORT_NOT_READY", "warnings": exc.warnings})
    if isinstance(exc, MenuImportValidationError):
        return HTTPException(422, {"code": "MENU_IMPORT_INVALID", "message": str(exc)})
    return HTTPException(400, "Menu import operation failed")


@router.post("/preview", response_model=MenuImportPreview)
async def preview_menu_import(
    file: Annotated[UploadFile, File()],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    sheet_name: Annotated[str | None, Form()] = None,
):
    del user
    try:
        payload = await file.read(MAX_FILE_SIZE + 1)
        return MenuImportPreview.model_validate(MenuImportService(session).preview(
            payload, file.filename or "upload.xlsx", sheet_name.strip() if sheet_name else None,
        ))
    except MenuImportValidationError as exc:
        raise HTTPException(422, {"code": "MENU_IMPORT_INVALID", "message": str(exc)}) from exc
    except Exception as exc:
        logger.exception("Unhandled menu import preview error")
        raise HTTPException(400, "Menu import preview failed") from exc


@router.post("", response_model=MenuImportBatchDetail, status_code=status.HTTP_201_CREATED)
async def create_menu_import_draft(
    file: Annotated[UploadFile, File()],
    expected_source_hash: Annotated[str, Form()],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    sheet_name: Annotated[str | None, Form()] = None,
):
    try:
        payload = await file.read(MAX_FILE_SIZE + 1)
        return MenuImportBatchDetail.model_validate(MenuImportService(session).create_draft(
            payload,
            file.filename or "upload.xlsx",
            sheet_name.strip() if sheet_name else None,
            expected_source_hash,
            user.id,
        ))
    except Exception as exc:
        if not isinstance(exc, (
            MenuImportValidationError, MenuImportHashMismatchError, MenuImportFatalError,
            MenuImportDuplicateError, MenuImportDishUnavailableError,
        )):
            logger.exception("Unhandled menu import draft creation error")
        raise mapped_error(exc) from exc


@router.get("", response_model=MenuImportBatchList)
def list_menu_import_drafts(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    del user
    items, total = MenuImportService(session).list(page, page_size)
    return MenuImportBatchList(
        items=[MenuImportBatchSummary.model_validate(item) for item in items],
        pagination=PaginationMeta(page=page, page_size=page_size, total=total),
    )


@router.get("/{batch_id}", response_model=MenuImportBatchDetail)
def get_menu_import_draft(
    batch_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    del user
    try:
        return MenuImportBatchDetail.model_validate(MenuImportService(session).detail(batch_id))
    except Exception as exc:
        raise mapped_error(exc) from exc


@router.patch("/{batch_id}/lines/{line_id}", response_model=MenuImportBatchDetail)
def resolve_menu_import_line(
    batch_id: uuid.UUID,
    line_id: uuid.UUID,
    data: MenuImportLineResolve,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        return MenuImportBatchDetail.model_validate(MenuImportService(session).resolve_line(
            batch_id, line_id, data.dish_id, user.id,
        ))
    except Exception as exc:
        raise mapped_error(exc) from exc


@router.post("/{batch_id}/lines/{line_id}/exclude", response_model=MenuImportBatchDetail)
def exclude_menu_import_line(
    batch_id: uuid.UUID,
    line_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        return MenuImportBatchDetail.model_validate(
            MenuImportService(session).exclude_line(batch_id, line_id, user.id)
        )
    except Exception as exc:
        raise mapped_error(exc) from exc


@router.post("/{batch_id}/lines/{line_id}/restore", response_model=MenuImportBatchDetail)
def restore_menu_import_line(
    batch_id: uuid.UUID,
    line_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        return MenuImportBatchDetail.model_validate(
            MenuImportService(session).restore_line(batch_id, line_id, user.id)
        )
    except Exception as exc:
        raise mapped_error(exc) from exc


@router.post("/{batch_id}/finalize", response_model=MenuImportFinalizeResponse)
def finalize_menu_import(
    batch_id: uuid.UUID,
    data: MenuImportFinalize,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        return MenuImportFinalizeResponse.model_validate(MenuImportService(session).finalize(
            batch_id, data.name, data.category_id, data.notes, user.id,
        ))
    except Exception as exc:
        if not isinstance(exc, (
            MenuImportValidationError, MenuImportNotFoundError, MenuImportNotReadyError,
        )):
            logger.exception("Unhandled menu import finalize error")
        raise mapped_error(exc) from exc


@router.delete("/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_menu_import_draft(
    batch_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    try:
        MenuImportService(session).delete_draft(batch_id, user.id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as exc:
        raise mapped_error(exc) from exc
