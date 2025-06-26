import pytest_asyncio
import httpx
import asyncio
from httpx_ws.transport import ASGIWebSocketTransport
from server import build_app, Settings


@pytest_asyncio.fixture(scope="function")
async def http_client():
    """HTTP client fixture for API calls."""
    settings = Settings(redis_url="redis://localhost:6379/0", ttl=60 * 60)
    app = build_app(settings)

    # Manually handle lifespan
    async with app.router.lifespan_context(app):
        transport = ASGIWebSocketTransport(app=app)
        client = httpx.AsyncClient(transport=transport, base_url="http://test")

        try:
            yield client
        finally:
            # Cancel any hanging tasks created by httpx_ws
            for task in asyncio.all_tasks():
                if "ASGIWebSocketAsyncNetworkStream" in str(
                    task
                ) or "buffer_live_events" in str(task):
                    task.cancel()

            # Clear transport exit stack to prevent cleanup issues
            if hasattr(transport, "exit_stack") and transport.exit_stack:
                transport.exit_stack = None

            # Now close the client with timeout
            try:
                await asyncio.wait_for(client.aclose(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
