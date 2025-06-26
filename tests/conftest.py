import pytest_asyncio
import httpx
from httpx_ws.transport import ASGIWebSocketTransport
from server import build_app, Settings


@pytest_asyncio.fixture
async def app():
    """Function-scoped app fixture."""
    settings = Settings(redis_url="redis://localhost:6379/0", ttl=60 * 60)
    app = build_app(settings)
    yield app

    # Clean up Redis after each test
    try:
        await app.state.redis_client.aclose()
    except Exception:
        pass


@pytest_asyncio.fixture
async def http_client(app):
    """HTTP client fixture for API calls."""
    transport = ASGIWebSocketTransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
