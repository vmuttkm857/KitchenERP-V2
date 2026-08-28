from typing import Literal

from pydantic import BaseModel, Field

from app.domains.users.schemas import UserPublic


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserPublic


class MessageResponse(BaseModel):
    message: str
