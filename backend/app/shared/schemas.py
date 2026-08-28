from pydantic import BaseModel, Field


class PasswordConfirmation(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
