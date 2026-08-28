from fastapi import FastAPI

from app.api.v1.router import api_v1_router
from app.core.config import settings


def create_app() -> FastAPI:
    application = FastAPI(title=settings.app_name, version="0.1.0")
    application.include_router(api_v1_router, prefix="/api/v1")
    return application


app = create_app()
