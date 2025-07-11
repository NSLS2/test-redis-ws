import json
import pytest
import numpy as np


def test_websocket_connection_to_non_existent_node(client):
    """Test websocket connection to non-existent node returns 404."""
    non_existent_node_id = "definitely_non_existent_websocket_node_99999999"
    
    # Try to connect to websocket for non-existent node
    # This should result in an HTTP 404 response during the handshake
    with pytest.raises(Exception) as exc_info:
        with client.websocket_connect(f"/stream/single/{non_existent_node_id}") as websocket:
            # If we get here, the connection was accepted when it shouldn't have been
            assert False, "Websocket connection should have been rejected"
    
    # The exception should be a Response object with 404 status code
    response = exc_info.value
    assert hasattr(response, 'status_code'), f"Expected Response object, got: {type(response)}"
    assert response.status_code == 404, f"Expected 404 status code, got: {response.status_code}"
    

def test_subscribe_immediately_after_creation_websockets(client):
    """Client that subscribes immediately after node creation sees all updates in order."""
    # Create node
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]

    # Connect WebSocket immediately
    with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
        # Write updates
        updates = []
        for i in range(1, 4):
            data = np.array([float(i), float(i + 1), float(i + 2)])
            client.post(
                f"/upload/{node_id}",
                content=data.tobytes(),
                headers={"Content-Type": "application/octet-stream"},
            )
            updates.append(data.tolist())

        # Receive all updates
        received = []
        for _ in range(3):
            msg_text = websocket.receive_text()
            msg = json.loads(msg_text)
            received.append(msg)

        # Verify all updates received in order
        assert len(received) == 3
        for i, (msg, expected_data) in enumerate(zip(received, updates)):
            assert msg["sequence"] == i + 1
            assert msg["payload"] == expected_data

    # Cleanup
    client.delete(f"/upload/{node_id}")


def test_subscribe_after_first_update_websockets(client):
    """Client that subscribes after first update sees only subsequent updates."""
    # Create node
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]

    # Write first update before subscribing
    first_data = np.array([1.0, 2.0, 3.0])
    client.post(
        f"/upload/{node_id}",
        content=first_data.tobytes(),
        headers={"Content-Type": "application/octet-stream"},
    )

    # Connect WebSocket after first update
    with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
        # Write more updates
        updates = []
        for i in range(2, 4):
            data = np.array([float(i), float(i + 1), float(i + 2)])
            client.post(
                f"/upload/{node_id}",
                content=data.tobytes(),
                headers={"Content-Type": "application/octet-stream"},
            )
            updates.append(data.tolist())

        # Should only receive the 2 new updates
        received = []
        for _ in range(2):
            msg_text = websocket.receive_text()
            msg = json.loads(msg_text)
            received.append(msg)

        # Verify only new updates received
        assert len(received) == 2
        assert received[0]["sequence"] == 2
        assert received[0]["payload"] == [2.0, 3.0, 4.0]
        assert received[1]["sequence"] == 3
        assert received[1]["payload"] == [3.0, 4.0, 5.0]

    # Cleanup
    client.delete(f"/upload/{node_id}")


def test_subscribe_after_first_update_from_beginning_websockets(client):
    """Client that subscribes after first update but requests from seq_num=0 sees all updates.

    Note: seq_num starts at 1 for the first data point. seq_num=0 means "start as far back
    as you have" (similar to Bluesky social)
    """
    # Create node
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]

    # Write first update before subscribing
    first_data = np.array([1.0, 2.0, 3.0])
    client.post(
        f"/upload/{node_id}",
        content=first_data.tobytes(),
        headers={"Content-Type": "application/octet-stream"},
    )

    # Connect WebSocket requesting from beginning
    with client.websocket_connect(f"/stream/single/{node_id}?seq_num=0") as websocket:
        # First, should receive the historical update
        historical_msg_text = websocket.receive_text()
        historical_msg = json.loads(historical_msg_text)
        assert historical_msg["sequence"] == 1
        assert historical_msg["payload"] == [1.0, 2.0, 3.0]

        # Write more updates
        updates = [[1.0, 2.0, 3.0]]  # Already have first one
        for i in range(2, 4):
            data = np.array([float(i), float(i + 1), float(i + 2)])
            client.post(
                f"/upload/{node_id}",
                content=data.tobytes(),
                headers={"Content-Type": "application/octet-stream"},
            )
            updates.append(data.tolist())

        # Receive the new updates
        for i in range(2, 4):
            msg_text = websocket.receive_text()
            msg = json.loads(msg_text)
            assert msg["sequence"] == i
            assert msg["payload"] == updates[i - 1]

    # Cleanup
    client.delete(f"/upload/{node_id}")
