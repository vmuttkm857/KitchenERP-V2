import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.domains.audit.exceptions import AuditLogNotFoundError
from app.domains.audit.schemas import AuditLogDetail, AuditLogList, AuditLogSummary
from app.domains.audit.service import AuditLogService
from app.domains.auth.dependencies import require_admin
from app.domains.users.models import User
from app.shared.schemas import PaginationMeta

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("", response_model=AuditLogList)
def list_audit_logs(session: Annotated[Session, Depends(get_db_session)], admin: Annotated[User, Depends(require_admin)],
                    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                    actor_user_id: uuid.UUID | None = None, action: str | None = None,
                    entity_type: str | None = None, date_from: date | None = None,
                    date_to: date | None = None, keyword: str | None = None):
    items, total = AuditLogService(session).list(page=page, page_size=page_size,
        actor_user_id=actor_user_id, action=action, entity_type=entity_type,
        date_from=date_from, date_to=date_to, keyword=keyword)
    return AuditLogList(items=[AuditLogSummary.model_validate(item) for item in items],
                        pagination=PaginationMeta(page=page, page_size=page_size, total=total))


@router.get("/{audit_id}", response_model=AuditLogDetail)
def get_audit_log(audit_id: uuid.UUID, session: Annotated[Session, Depends(get_db_session)],
                  admin: Annotated[User, Depends(require_admin)]):
    try:
        item = AuditLogService(session).get(audit_id)
        return AuditLogDetail(
            id=item.id, actor_user_id=item.actor_user_id, actor_username=item.actor_username,
            actor_display_name=item.actor_display_name, action=item.action, entity_type=item.entity_type,
            entity_id=item.entity_id, entity_label=item.entity_label, created_at=item.created_at,
            before_data=item.before_data, after_data=item.after_data, metadata=item.metadata_data,
            request_id=item.request_id, ip_address=item.ip_address,
        )
    except AuditLogNotFoundError as exc:
        raise HTTPException(404, "Audit log not found") from exc
