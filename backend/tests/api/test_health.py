import asyncio

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.api.v1.routes.health import get_readiness_service
from app.core.readiness import ReadinessResult
from app.main import app


def test_health_endpoint() -> None:
    async def request_health():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/v1/health")

    response = asyncio.run(request_health())

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "kitchenerp-v2-api",
        "version": "0.1.0",
    }


class StubReadinessService:
    def __init__(self, result: ReadinessResult) -> None:
        self.result = result

    def check(self) -> ReadinessResult:
        return self.result


def test_readiness_database_and_schema_healthy(client: TestClient) -> None:
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["checks"] == {"database": "ok", "schema": "ok"}


def test_readiness_database_unavailable(client: TestClient) -> None:
    app.dependency_overrides[get_readiness_service] = lambda: StubReadinessService(
        ReadinessResult(database_ok=False, schema_ok=False)
    )
    try:
        response = client.get("/api/v1/ready")
    finally:
        app.dependency_overrides.pop(get_readiness_service, None)
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "failed", "schema": "failed"}


def test_readiness_wrong_schema_revision(client: TestClient) -> None:
    app.dependency_overrides[get_readiness_service] = lambda: StubReadinessService(
        ReadinessResult(database_ok=True, schema_ok=False)
    )
    try:
        response = client.get("/api/v1/ready")
    finally:
        app.dependency_overrides.pop(get_readiness_service, None)
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "ok", "schema": "failed"}
