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
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            yield client
        finally:
            # Workaround for httpx-ws issue: https://github.com/frankie567/httpx-ws/discussions/79
            # ASGIWebSocketTransport doesn't properly clean up its exit_stack when the client closes,
            # causing "Attempted to exit cancel scope in different task" errors
            if hasattr(transport, "exit_stack") and transport.exit_stack:
                transport.exit_stack = None
