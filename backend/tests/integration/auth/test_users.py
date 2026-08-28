import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.auth.passwords import hash_password
from app.domains.users.models import User
from app.domains.users.schemas import CreateUserCommand
from app.domains.users.service import UserService


def test_create_user(db_session: Session) -> None:
    user = UserService(db_session).create_user(
        CreateUserCommand(
            username="First.Admin",
            password="a secure password for testing",
            display_name="First Admin",
            role="admin",
        )
    )

    saved = db_session.scalar(select(User).where(User.id == user.id))
    assert saved is not None
    assert saved.username == "first.admin"
    assert saved.role == "admin"
    assert saved.password_hash != "a secure password for testing"


def test_database_enforces_unique_username(db_session: Session) -> None:
    db_session.add_all(
        [
            User(
                username="duplicate",
                password_hash=hash_password("first secure testing password"),
                display_name="One",
                role="user",
            ),
            User(
                username="duplicate",
                password_hash=hash_password("second secure testing password"),
                display_name="Two",
                role="user",
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
