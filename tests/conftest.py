import pytest
from starlette.testclient import TestClient
from server import build_app, Settings


@pytest.fixture(scope="function")
def client():
    """Fixture providing TestClient following ws-tests pattern."""
    settings = Settings(redis_url="redis://localhost:6379/0", ttl=60 * 60)
    app = build_app(settings)

    with TestClient(app) as client:
        yield client
