import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.auth.exceptions import (
    InvalidAccessTokenError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)
from app.domains.auth.models import RefreshSession
from app.domains.auth.passwords import verify_password, verify_unknown_user_password
from app.domains.auth.repository import RefreshSessionRepository
from app.domains.auth.tokens import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_refresh_token,
)
from app.domains.users.models import User
from app.domains.users.repository import UserRepository


@dataclass(frozen=True)
class AuthResult:
    access_token: str
    refresh_token: str
    user: User


class AuthService:
    def __init__(
        self,
        session: Session,
        user_repository: UserRepository | None = None,
        refresh_repository: RefreshSessionRepository | None = None,
    ) -> None:
        self.session = session
        self.users = user_repository or UserRepository(session)
        self.refresh_sessions = refresh_repository or RefreshSessionRepository(session)

    def login(self, username: str, password: str) -> AuthResult:
        user = self.users.get_by_username(username.strip().lower())
        if user is None:
            verify_unknown_user_password(password)
            raise InvalidCredentialsError("Invalid username or password")
        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("Invalid username or password")
        if not user.is_active:
            raise InvalidCredentialsError("Invalid username or password")

        now = datetime.now(UTC)
        plaintext_refresh = create_refresh_token()
        self.refresh_sessions.add(
            RefreshSession(
                user_id=user.id,
                token_hash=hash_refresh_token(plaintext_refresh),
                expires_at=now + timedelta(days=settings.refresh_token_days),
            )
        )
        self.session.commit()
        return AuthResult(
            access_token=create_access_token(user.id, user.role, now),
            refresh_token=plaintext_refresh,
            user=user,
        )

    def refresh(self, plaintext_refresh: str) -> AuthResult:
        now = datetime.now(UTC)
        current = self.refresh_sessions.get_by_hash_for_update(
            hash_refresh_token(plaintext_refresh)
        )
        if current is None or current.revoked_at is not None or current.expires_at <= now:
            raise InvalidRefreshTokenError("Invalid refresh token")

        user = self.users.get_by_id(current.user_id)
        if user is None or not user.is_active:
            raise InvalidRefreshTokenError("Invalid refresh token")

        next_plaintext = create_refresh_token()
        next_session = RefreshSession(
            user_id=user.id,
            token_hash=hash_refresh_token(next_plaintext),
            expires_at=now + timedelta(days=settings.refresh_token_days),
        )
        self.refresh_sessions.add(next_session)
        self.session.flush()

        current.revoked_at = now
        current.last_used_at = now
        current.rotated_to_id = next_session.id
        self.session.commit()

        return AuthResult(
            access_token=create_access_token(user.id, user.role, now),
            refresh_token=next_plaintext,
            user=user,
        )

    def logout(self, plaintext_refresh: str | None) -> None:
        if plaintext_refresh:
            current = self.refresh_sessions.get_by_hash_for_update(
                hash_refresh_token(plaintext_refresh)
            )
            if current is not None and current.revoked_at is None:
                current.revoked_at = datetime.now(UTC)
                current.last_used_at = current.revoked_at
        self.session.commit()

    def get_current_user(self, access_token: str) -> User:
        try:
            user_id = decode_access_token(access_token)
        except InvalidAccessTokenError:
            raise
        user = self.users.get_by_id(user_id)
        if user is None or not user.is_active:
            raise InvalidAccessTokenError("Invalid access token")
        return user

    def verify_current_password(self, user_id: uuid.UUID, password: str) -> User:
        user = self.users.get_by_id(user_id)
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("Password verification failed")
        return user

    def revoke_all_sessions(self, user_id: uuid.UUID) -> int:
        count = self.refresh_sessions.revoke_all_for_user(user_id, datetime.now(UTC))
        self.session.commit()
        return count
