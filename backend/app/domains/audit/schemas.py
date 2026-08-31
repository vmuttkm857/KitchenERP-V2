import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.shared.schemas import PaginationMeta


class AuditLogSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_username: str
    actor_display_name: str
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    entity_label: str | None
    created_at: datetime


class AuditLogDetail(AuditLogSummary):
    before_data: dict[str, Any] | None
    after_data: dict[str, Any] | None
    metadata: dict[str, Any]
    request_id: str | None
    ip_address: str | None


class AuditLogList(BaseModel):
    items: list[AuditLogSummary]
    pagination: PaginationMeta
