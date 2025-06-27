import pytest_asyncio
import httpx
from httpx_ws.transport import ASGIWebSocketTransport
from server import build_app, Settings


@pytest_asyncio.fixture(scope="function")
async def http_client():
    """HTTP client fixture for API calls."""
    settings = Settings(redis_url="redis://localhost:6379/0", ttl=60 * 60)
    app = build_app(settings)

    transport = ASGIWebSocketTransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")

    try:
        yield client
    finally:
        # Clear transport exit stack to prevent cleanup issues with httpx_ws
        if hasattr(transport, "exit_stack") and transport.exit_stack:
            transport.exit_stack = None

        await client.aclose()
