import pytest_asyncio
import httpx
from server import build_app, Settings


@pytest_asyncio.fixture(scope="module")
async def test_client():
    """Simplest possible test client setup."""
    settings = Settings(redis_url="redis://localhost:6379/0", ttl=60 * 60)
    app = build_app(settings)
    
    from httpx_ws.transport import ASGIWebSocketTransport
    transport = ASGIWebSocketTransport(app=app)
    
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
