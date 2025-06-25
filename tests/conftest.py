import pytest_asyncio
from server import build_app, Settings

@pytest_asyncio.fixture
async def app():
    """Function-scoped app fixture following reference pattern."""
    settings = Settings(redis_url="redis://localhost:6379/0", ttl=60 * 60)
    app = build_app(settings)
    yield app
    
    # Clean up Redis after each test
    try:
        await app.state.redis_client.aclose()
    except Exception:
        pass
