import pytest
import pytest_asyncio
import redis
import httpx
import asyncio
from server import build_app, Settings


@pytest.fixture
def redis_client():
    """Redis client for test cleanup and verification."""
    client = redis.from_url("redis://localhost:6379/0")
    return client


@pytest.fixture(autouse=True)
def clean_redis(redis_client):
    """Automatically clean Redis before each test."""
    redis_client.flushdb()
    yield
    redis_client.flushdb()


@pytest_asyncio.fixture(scope="function")
async def test_settings():
    """Test-specific settings."""
    return Settings(
        redis_url="redis://localhost:6379/0",
        ttl=60 * 60
    )


@pytest_asyncio.fixture(scope="function")
async def test_app(test_settings):
    """FastAPI app instance for tests."""
    app = build_app(test_settings)
    yield app


@pytest_asyncio.fixture(scope="function")
async def test_client(test_app):
    """Async ASGI client for testing."""
    from httpx_ws.transport import ASGIWebSocketTransport
    transport = ASGIWebSocketTransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
        # Brief pause to allow cleanup
        await asyncio.sleep(0.1)
