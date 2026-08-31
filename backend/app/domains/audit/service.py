import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.domains.audit.context import get_audit_request_context
from app.domains.audit.exceptions import AuditLogNotFoundError
from app.domains.audit.models import AuditLog
from app.domains.audit.repository import AuditLogRepository
from app.domains.audit.sanitization import sanitize_audit_data
from app.domains.users.models import User


class AuditLogService:
    def __init__(self, session: Session, repository: AuditLogRepository | None = None) -> None:
        self.session = session
        self.repository = repository or AuditLogRepository(session)

    def record(
        self, *, actor_id: uuid.UUID | None, action: str, entity_type: str,
        entity_id: uuid.UUID | None = None, entity_label: str | None = None,
        before_data: Any = None, after_data: Any = None, metadata: Any = None,
    ) -> AuditLog:
        # Reading the actor must not trigger an early autoflush of the business
        # mutation.  The owning service remains responsible for the one commit.
        with self.session.no_autoflush:
            actor = self.session.get(User, actor_id) if actor_id is not None else None
        context = get_audit_request_context()
        value = AuditLog(
            actor_user_id=actor.id if actor else None,
            actor_username=actor.username if actor else "system",
            actor_display_name=actor.display_name if actor else "System / Bootstrap",
            action=action, entity_type=entity_type, entity_id=entity_id,
            entity_label=entity_label,
            before_data=sanitize_audit_data(before_data) if before_data is not None else None,
            after_data=sanitize_audit_data(after_data) if after_data is not None else None,
            metadata_data=sanitize_audit_data(metadata or {}),
            request_id=context.request_id, ip_address=context.ip_address,
        )
        self.repository.add(value)
        return value

    def list(self, *, page: int, page_size: int, actor_user_id: uuid.UUID | None,
             action: str | None, entity_type: str | None, date_from: date | None,
             date_to: date | None, keyword: str | None):
        start = datetime.combine(date_from, time.min, tzinfo=UTC) if date_from else None
        end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC) if date_to else None
        return self.repository.list(page=page, page_size=page_size, actor_user_id=actor_user_id,
                                    action=action, entity_type=entity_type, date_from=start,
                                    date_to=end, keyword=keyword)

    def get(self, audit_id: uuid.UUID) -> AuditLog:
        value = self.repository.get(audit_id)
        if value is None:
            raise AuditLogNotFoundError()
        return value


def audit_snapshot(value: object, *fields: str) -> dict[str, Any]:
    return {field: getattr(value, field) for field in fields}
