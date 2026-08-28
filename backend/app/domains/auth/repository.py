import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domains.auth.models import RefreshSession


class RefreshSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, refresh_session: RefreshSession) -> None:
        self.session.add(refresh_session)

    def get_by_hash_for_update(self, token_hash: str) -> RefreshSession | None:
        statement = (
            select(RefreshSession)
            .where(RefreshSession.token_hash == token_hash)
            .with_for_update()
        )
        return self.session.scalar(statement)

    def revoke_all_for_user(self, user_id: uuid.UUID, revoked_at: datetime) -> int:
        statement = (
            update(RefreshSession)
            .where(RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )
        result = self.session.execute(statement)
        return result.rowcount
