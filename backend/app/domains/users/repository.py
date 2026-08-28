import uuid

from sqlalchemy import select
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
