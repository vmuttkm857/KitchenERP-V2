import asyncio

from httpx import ASGITransport, AsyncClient

from app.main import app


def test_health_endpoint() -> None:
    async def request_health():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/v1/health")

    response = asyncio.run(request_health())

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "kitchenerp-v2-api"}
