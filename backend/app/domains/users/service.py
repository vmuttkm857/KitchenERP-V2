import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.audit.service import AuditLogService, audit_snapshot
from app.domains.auth.passwords import hash_password
from app.domains.auth.service import AuthService
from app.domains.users.exceptions import LastActiveAdminError, UserNotFoundError, UsernameAlreadyExistsError
from app.domains.users.models import User
from app.domains.users.repository import UserRepository
from app.domains.users.schemas import CreateUserCommand, PasswordChange, PasswordReset, UserUpdate


USER_AUDIT_FIELDS = ("username", "display_name", "role", "is_active")


class UserService:
    def __init__(self, session: Session, repository: UserRepository | None = None) -> None:
        self.session = session
        self.repository = repository or UserRepository(session)
        self.audit = AuditLogService(session)
        self.auth = AuthService(session, user_repository=self.repository)

    def get(self, user_id: uuid.UUID) -> User:
        user = self.repository.get_by_id(user_id)
        if user is None: raise UserNotFoundError()
        return user

    def list(self, page: int, page_size: int, search: str | None, active: bool | None,
             role: str | None) -> tuple[list[User], int]:
        return self.repository.list(page, page_size, search, active, role)

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
            self.session.flush()
            self.audit.record(actor_id=actor_id, action="user_created", entity_type="user",
                              entity_id=user.id, entity_label=user.username,
                              after_data=audit_snapshot(user, *USER_AUDIT_FIELDS))
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise UsernameAlreadyExistsError("Username already exists") from exc
        self.session.refresh(user)
        return user

    def update(self, user_id: uuid.UUID, data: UserUpdate, actor_id: uuid.UUID) -> User:
        user = self.get(user_id)
        before = audit_snapshot(user, *USER_AUDIT_FIELDS)
        changes = data.model_dump(exclude_unset=True)
        if changes.get("display_name") is None: changes.pop("display_name", None)
        else: changes["display_name"] = changes["display_name"].strip()
        if changes.get("role") is None: changes.pop("role", None)
        if changes.get("role") == "user" and user.role == "admin" and user.is_active:
            self._ensure_not_last_admin(user.id)
        for field, value in changes.items(): setattr(user, field, value)
        user.updated_by = actor_id
        action = "user_role_changed" if before["role"] != user.role else "user_updated"
        self.audit.record(actor_id=actor_id, action=action, entity_type="user", entity_id=user.id,
                          entity_label=user.username, before_data=before,
                          after_data=audit_snapshot(user, *USER_AUDIT_FIELDS))
        self.session.commit(); self.session.refresh(user); return user

    def set_active(self, user_id: uuid.UUID, active: bool, actor_id: uuid.UUID) -> User:
        user = self.get(user_id); before = audit_snapshot(user, *USER_AUDIT_FIELDS)
        if not active and user.role == "admin" and user.is_active: self._ensure_not_last_admin(user.id)
        user.is_active = active; user.updated_by = actor_id
        if not active: self.auth.revoke_all_sessions(user.id)
        self.audit.record(actor_id=actor_id, action="user_reactivated" if active else "user_deactivated",
                          entity_type="user", entity_id=user.id, entity_label=user.username,
                          before_data=before, after_data=audit_snapshot(user, *USER_AUDIT_FIELDS))
        self.session.commit(); self.session.refresh(user); return user

    def reset_password(self, user_id: uuid.UUID, data: PasswordReset, actor_id: uuid.UUID) -> User:
        self.auth.verify_current_password(actor_id, data.current_admin_password)
        user = self.get(user_id); user.password_hash = hash_password(data.new_password); user.updated_by = actor_id
        self.auth.revoke_all_sessions(user.id)
        self.audit.record(actor_id=actor_id, action="password_reset", entity_type="user",
                          entity_id=user.id, entity_label=user.username,
                          after_data={"credential_changed": True})
        self.session.commit(); self.session.refresh(user); return user

    def change_password(self, user_id: uuid.UUID, data: PasswordChange) -> None:
        user = self.auth.verify_current_password(user_id, data.current_password)
        user.password_hash = hash_password(data.new_password); user.updated_by = user_id
        self.auth.revoke_all_sessions(user.id)
        self.audit.record(actor_id=user_id, action="password_changed", entity_type="user",
                          entity_id=user.id, entity_label=user.username,
                          after_data={"credential_changed": True})
        self.session.commit()

    def _ensure_not_last_admin(self, target_id: uuid.UUID) -> None:
        active_admins = self.repository.lock_active_admins()
        if len(active_admins) == 1 and active_admins[0].id == target_id:
            raise LastActiveAdminError()
