import logging
import time
import uuid

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.domains.auth.exceptions import AuthenticationError
from app.domains.audit.context import AuditRequestContext, reset_audit_request_context, set_audit_request_context


logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("kitchenerp.request")


def create_app() -> FastAPI:
    application = FastAPI(title=settings.app_name, version=settings.app_version)

    @application.middleware("http")
    async def request_observability(request: Request, call_next):
        request_id = str(uuid.uuid4())
        peer_ip = request.client.host if request.client is not None else None
        audit_token = set_audit_request_context(AuditRequestContext(request_id=request_id, ip_address=peer_ip))
        started = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                logger.error(
                    "request_failed method=%s path=%s request_id=%s exception_type=%s",
                    request.method,
                    request.url.path,
                    request_id,
                    type(exc).__name__,
                )
                response = JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={"detail": "Internal server error", "request_id": request_id},
                    headers={"X-Request-ID": request_id},
                )
            duration_ms = (time.perf_counter() - started) * 1000
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "request method=%s path=%s status=%s duration_ms=%.2f request_id=%s",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                request_id,
            )
            return response
        finally:
            reset_audit_request_context(audit_token)

    @application.exception_handler(AuthenticationError)
    async def authentication_error_handler(
        request: Request, exc: AuthenticationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Authentication failed"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    application.include_router(api_v1_router, prefix="/api/v1")
    return application


app = create_app()
