import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.schemas import PaginationMeta


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str
    role: Literal["admin", "user"]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CreateUserCommand(BaseModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=1024)
    display_name: str = Field(min_length=1, max_length=150)
    role: Literal["admin", "user"] = "user"


class UserCreate(CreateUserCommand):
    confirm_password: str = Field(min_length=12, max_length=1024)

    @model_validator(mode="after")
    def matching_passwords(self) -> "UserCreate":
        if self.password != self.confirm_password: raise ValueError("Passwords do not match")
        return self


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=150)
    role: Literal["admin", "user"] | None = None


class PasswordReset(BaseModel):
    current_admin_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)
    confirm_password: str = Field(min_length=12, max_length=1024)

    @model_validator(mode="after")
    def matching_passwords(self) -> "PasswordReset":
        if self.new_password != self.confirm_password: raise ValueError("Passwords do not match")
        return self


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)
    confirm_password: str = Field(min_length=12, max_length=1024)

    @model_validator(mode="after")
    def matching_passwords(self) -> "PasswordChange":
        if self.new_password != self.confirm_password: raise ValueError("Passwords do not match")
        return self


class UserList(BaseModel):
    items: list[UserPublic]
    pagination: PaginationMeta
