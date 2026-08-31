from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domains.users.models import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, user: User) -> None:
        self.session.add(user)

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.session.get(User, user_id)

    def get_by_username(self, username: str) -> User | None:
        statement = select(User).where(User.username == username)
        return self.session.scalar(statement)

    def username_exists(self, username: str) -> bool:
        statement = select(User.id).where(User.username == username).limit(1)
        return self.session.scalar(statement) is not None

    def list(self, page: int, page_size: int, search: str | None, active: bool | None,
             role: str | None) -> tuple[list[User], int]:
        filters = []
        if search and search.strip():
            term = f"%{search.strip()}%"
            filters.append(or_(User.username.ilike(term), User.display_name.ilike(term)))
        if active is not None: filters.append(User.is_active == active)
        if role: filters.append(User.role == role)
        total = self.session.scalar(select(func.count()).select_from(User).where(*filters)) or 0
        statement = (select(User).where(*filters).order_by(User.updated_at.desc(), User.id)
                     .offset((page - 1) * page_size).limit(page_size))
        return list(self.session.scalars(statement)), total

    def lock_active_admins(self) -> list[User]:
        statement = (select(User).where(User.role == "admin", User.is_active.is_(True))
                     .order_by(User.id).with_for_update())
        return list(self.session.scalars(statement))
