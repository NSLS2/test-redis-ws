import json
import numpy as np
import pytest
from fastapi.testclient import TestClient
from server import build_app, Settings


def test_subscribe_immediately_after_creation():
    """Test subscribing immediately after node creation sees all updates."""
    settings = Settings(redis_url="redis://localhost:6379/0", ttl=3600)
    app = build_app(settings)
    client = TestClient(app)

    # Create a new node
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]

    # Subscribe to WebSocket immediately (before any data written)
    with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
        # Write first data chunk
        test_data_1 = np.array([1.0, 2.0, 3.0])
        response = client.post(
            f"/upload/{node_id}",
            content=test_data_1.tobytes(),
            headers={"Content-Type": "application/octet-stream"}
        )
        assert response.status_code == 200

        # Write second data chunk
        test_data_2 = np.array([4.0, 5.0, 6.0])
        response = client.post(
            f"/upload/{node_id}",
            content=test_data_2.tobytes(),
            headers={"Content-Type": "application/octet-stream"}
        )
        assert response.status_code == 200

        # Receive first message
        message_1 = websocket.receive_text()
        data_1 = json.loads(message_1)
        assert data_1["sequence"] == 1
        assert data_1["payload"] == [1.0, 2.0, 3.0]

        # Receive second message
        message_2 = websocket.receive_text()
        data_2 = json.loads(message_2)
        assert data_2["sequence"] == 2
        assert data_2["payload"] == [4.0, 5.0, 6.0]

    # Clean up the Redis data for this node
    client.delete(f"/upload/{node_id}")

