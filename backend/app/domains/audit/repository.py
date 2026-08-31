import uuid
from datetime import datetime

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.domains.audit.models import AuditLog


class AuditLogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, value: AuditLog) -> None:
        self.session.add(value)

    def get(self, audit_id: uuid.UUID) -> AuditLog | None:
        return self.session.get(AuditLog, audit_id)

    def list(
        self, *, page: int, page_size: int, actor_user_id: uuid.UUID | None,
        action: str | None, entity_type: str | None, date_from: datetime | None,
        date_to: datetime | None, keyword: str | None,
    ) -> tuple[list[AuditLog], int]:
        filters = []
        if actor_user_id is not None:
            filters.append(AuditLog.actor_user_id == actor_user_id)
        if action:
            filters.append(AuditLog.action == action)
        if entity_type:
            filters.append(AuditLog.entity_type == entity_type)
        if date_from is not None:
            filters.append(AuditLog.created_at >= date_from)
        if date_to is not None:
            filters.append(AuditLog.created_at < date_to)
        if keyword and keyword.strip():
            term = f"%{keyword.strip()}%"
            filters.append(or_(
                AuditLog.actor_username.ilike(term), AuditLog.actor_display_name.ilike(term),
                AuditLog.entity_label.ilike(term), AuditLog.action.ilike(term),
                AuditLog.entity_type.ilike(term), cast(AuditLog.entity_id, String).ilike(term),
            ))
        total = self.session.scalar(select(func.count()).select_from(AuditLog).where(*filters)) or 0
        statement = (
            select(AuditLog).where(*filters)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )
        return list(self.session.scalars(statement)), total
