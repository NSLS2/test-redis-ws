import json
import numpy as np
import pytest
import asyncio
from httpx_ws import aconnect_ws


@pytest.mark.asyncio
async def test_subscribe_immediately_after_creation(http_client):
    """Client that subscribes immediately after node creation sees all updates in order."""
    # Create node
    response = await http_client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]

    # Connect WebSocket immediately
    async with aconnect_ws(f"/stream/single/{node_id}", http_client) as ws:
        # Small delay to ensure WebSocket subscription is established
        await asyncio.sleep(0.1)

        # Write updates
        updates = []
        for i in range(1, 4):
            data = np.array([float(i), float(i + 1), float(i + 2)])
            await http_client.post(
                f"/upload/{node_id}",
                content=data.tobytes(),
                headers={"Content-Type": "application/octet-stream"},
            )
            updates.append(data.tolist())

        # Receive all updates
        received = []
        for _ in range(3):
            msg = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=2.0))
            received.append(msg)

        # Verify all updates received in order
        assert len(received) == 3
        for i, (msg, expected_data) in enumerate(zip(received, updates)):
            assert msg["sequence"] == i + 1
            assert msg["payload"] == expected_data

    # Cleanup
    await http_client.delete(f"/upload/{node_id}")


@pytest.mark.asyncio
async def test_subscribe_after_first_update(http_client):
    """Client that subscribes after first update sees only subsequent updates."""
    # Create node
    response = await http_client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]

    # Write first update before subscribing
    first_data = np.array([1.0, 2.0, 3.0])
    await http_client.post(
        f"/upload/{node_id}",
        content=first_data.tobytes(),
        headers={"Content-Type": "application/octet-stream"},
    )

    # Small delay to ensure first update is processed
    await asyncio.sleep(0.1)

    # Connect WebSocket after first update
    async with aconnect_ws(f"/stream/single/{node_id}", http_client) as ws:
        # Small delay to ensure WebSocket subscription is established
        await asyncio.sleep(0.1)

        # Write more updates
        updates = []
        for i in range(2, 4):
            data = np.array([float(i), float(i + 1), float(i + 2)])
            await http_client.post(
                f"/upload/{node_id}",
                content=data.tobytes(),
                headers={"Content-Type": "application/octet-stream"},
            )
            updates.append(data.tolist())

        # Should only receive the 2 new updates
        received = []
        for _ in range(2):
            msg = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=2.0))
            received.append(msg)

        # Verify only new updates received
        assert len(received) == 2
        assert received[0]["sequence"] == 2
        assert received[0]["payload"] == [2.0, 3.0, 4.0]
        assert received[1]["sequence"] == 3
        assert received[1]["payload"] == [3.0, 4.0, 5.0]

    # Cleanup
    await http_client.delete(f"/upload/{node_id}")


@pytest.mark.asyncio
async def test_subscribe_after_first_update_from_beginning(http_client):
    """Client that subscribes after first update but requests from seq_num=1 sees all updates."""
    # Create node
    response = await http_client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]

    # Write first update before subscribing
    first_data = np.array([1.0, 2.0, 3.0])
    await http_client.post(
        f"/upload/{node_id}",
        content=first_data.tobytes(),
        headers={"Content-Type": "application/octet-stream"},
    )

    # Small delay to ensure first update is processed
    await asyncio.sleep(0.1)

    # Connect WebSocket requesting from beginning
    async with aconnect_ws(f"/stream/single/{node_id}?seq_num=1", http_client) as ws:
        # First, should receive the historical update
        historical_msg = json.loads(
            await asyncio.wait_for(ws.receive_text(), timeout=2.0)
        )
        assert historical_msg["sequence"] == 1
        assert historical_msg["payload"] == [1.0, 2.0, 3.0]

        # Write more updates
        updates = [[1.0, 2.0, 3.0]]  # Already have first one
        for i in range(2, 4):
            data = np.array([float(i), float(i + 1), float(i + 2)])
            await http_client.post(
                f"/upload/{node_id}",
                content=data.tobytes(),
                headers={"Content-Type": "application/octet-stream"},
            )
            updates.append(data.tolist())

        # Receive the new updates
        for i in range(2, 4):
            msg = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=2.0))
            assert msg["sequence"] == i
            assert msg["payload"] == updates[i - 1]

    # Cleanup
    await http_client.delete(f"/upload/{node_id}")
