import json
import numpy as np
import pytest
import asyncio
from httpx_ws import aconnect_ws


@pytest.mark.asyncio
async def test_simple_websocket_communication(http_client):
    """Test basic WebSocket communication: create node, connect, write data, receive message."""

    # Step 1: Create a new node via API
    response = await http_client.post("/upload")
    assert response.status_code == 200
    node_data = response.json()
    node_id = node_data["node_id"]

    # Step 2: Connect to WebSocket for this node
    async with aconnect_ws(f"/stream/single/{node_id}", http_client) as ws:
        # Small delay to ensure connection is established
        await asyncio.sleep(0.1)

        # Step 3: Write some data
        test_data = np.array([1.0, 2.0, 3.0])
        await http_client.post(
            f"/upload/{node_id}",
            content=test_data.tobytes(),
            headers={"Content-Type": "application/octet-stream"},
        )

        # Step 4: Read the message from WebSocket
        message = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=5.0))

        # Step 5: Verify the message
        assert message["sequence"] == 1
        assert message["payload"] == [1.0, 2.0, 3.0]
        assert "metadata" in message

    # Cleanup the node
    await http_client.delete(f"/upload/{node_id}")
