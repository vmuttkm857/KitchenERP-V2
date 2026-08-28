import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.auth.passwords import hash_password
from app.domains.users.exceptions import UsernameAlreadyExistsError
from app.domains.users.models import User
from app.domains.users.repository import UserRepository
from app.domains.users.schemas import CreateUserCommand


class UserService:
    def __init__(self, session: Session, repository: UserRepository | None = None) -> None:
        self.session = session
        self.repository = repository or UserRepository(session)

    def create_user(
        self,
        command: CreateUserCommand,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> User:
        username = command.username.strip().lower()
        if self.repository.username_exists(username):
            raise UsernameAlreadyExistsError("Username already exists")

        user = User(
            username=username,
            password_hash=hash_password(command.password),
            display_name=command.display_name.strip(),
            role=command.role,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self.repository.add(user)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise UsernameAlreadyExistsError("Username already exists") from exc
        self.session.refresh(user)
        return user
