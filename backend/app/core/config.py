from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "KitchenERP V2 API"
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://kitchenerp@localhost:5432/kitchenerp_v2"
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=5, ge=0)
    db_pool_timeout_seconds: int = Field(default=30, ge=1)
    db_echo: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
