import pytest_asyncio
import httpx
import asyncio
import socket
import uvicorn
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


def find_free_port():
    """Find a free port for the test server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


@pytest_asyncio.fixture(scope="function")
async def websocket_server():
    """WebSocket server fixture for websockets library tests."""
    settings = Settings(redis_url="redis://localhost:6379/0", ttl=60 * 60)
    app = build_app(settings)
    port = find_free_port()
    
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    
    # Wait for server to start
    while not server.started:
        await asyncio.sleep(0.01)
    
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            yield {"client": client, "port": port, "base_url": f"ws://127.0.0.1:{port}"}
    finally:
        server.should_exit = True
        server_task.cancel()
        try:
            await asyncio.wait_for(server_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
