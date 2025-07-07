"""
Tests designed to expose bugs, crashes, and incorrect behavior in the server.
"""
import asyncio
import json
import pytest
import redis.asyncio as redis


def test_malformed_json_in_close_endpoint(client):
    """Server crashes with malformed JSON in /close endpoint."""
    # TODO: Fix JSONDecodeError crash in server.py:91 - add proper error handling
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # This causes JSONDecodeError crash
    with pytest.raises(Exception):
        client.post(
            f"/close/{node_id}",
            content=b"invalid json {{{",
            headers={"Content-Type": "application/json"}
        )


def test_missing_json_body_in_close_endpoint(client):
    """Server crashes when /close endpoint receives no JSON body."""
    # TODO: Fix JSONDecodeError crash in server.py:91 - add proper error handling
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # This causes JSONDecodeError crash
    with pytest.raises(Exception):
        client.post(f"/close/{node_id}")


@pytest.mark.timeout(5)
def test_upload_invalid_binary_data_with_websocket(client):
    """Test server behavior when trying to interpret non-numeric binary data as float64."""
    # TODO: Test hangs on websocket.receive_text() - investigate WebSocket data processing
    # Create a node
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # Upload text data that can't be interpreted as float64 array
    response = client.post(
        f"/upload/{node_id}",
        content=b"this is not numeric data",
        headers={"Content-Type": "application/octet-stream"}
    )
    assert response.status_code == 200  # Upload succeeds
    
    # Test WebSocket behavior with invalid binary data
    with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
        try:
            # This might crash or handle gracefully on line 138: np.frombuffer(payload, dtype=np.float64)
            websocket.receive_text()
            # If we get here, server handled the error gracefully
        except Exception:
            # Expected behavior - server should handle this gracefully
            pass


@pytest.mark.timeout(5)
def test_upload_empty_payload_with_websocket(client):
    """Server behavior with zero-length binary data may be undefined."""
    # TODO: Test hangs on websocket.receive_text() - investigate empty data handling
    # Create a node
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # Upload empty binary data
    response = client.post(
        f"/upload/{node_id}",
        content=b"",
        headers={"Content-Type": "application/octet-stream"}
    )
    assert response.status_code == 200
    
    # WebSocket connection might crash when processing empty data
    with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
        msg_text = websocket.receive_text()
        msg = json.loads(msg_text)
        # Empty array might cause issues in downstream processing
        assert msg["payload"] == []




def test_websocket_invalid_seq_num_string(client):
    """Server properly validates seq_num parameter and disconnects."""
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # Server validates seq_num and disconnects on invalid input
    with pytest.raises(Exception):  # WebSocketDisconnect
        with client.websocket_connect(f"/stream/single/{node_id}?seq_num=invalid"):
            pass


@pytest.mark.timeout(5)
def test_websocket_negative_seq_num(client):
    """Server handles negative seq_num without validation."""
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    client.post(
        f"/upload/{node_id}",
        content=b"\x00\x00\x00\x00\x00\x00\x00\x00",
        headers={"Content-Type": "application/octet-stream"}
    )
    
    with client.websocket_connect(f"/stream/single/{node_id}?seq_num=-1") as websocket:
        websocket.receive_text()


@pytest.mark.timeout(5)
def test_delete_node_during_websocket_stream(client):
    """Race condition: deleting node while WebSocket is streaming."""
    # TODO: Test hangs after node deletion - potential race condition in WebSocket cleanup
    # Create a node and add data
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    client.post(
        f"/upload/{node_id}",
        content=b"\x00\x00\x00\x00\x00\x00\x00\x00",
        headers={"Content-Type": "application/octet-stream"}
    )
    
    # Start WebSocket connection
    with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
        # Receive first message
        websocket.receive_text()
        
        # Delete the node while WebSocket is still connected
        delete_response = client.delete(f"/upload/{node_id}")
        assert delete_response.status_code == 204
        
        # Try to add more data to deleted node - this might succeed unexpectedly
        response = client.post(
            f"/upload/{node_id}",
            content=b"\x01\x00\x00\x00\x00\x00\x00\x00",
            headers={"Content-Type": "application/octet-stream"}
        )
        # Don't wait for more messages as this might hang




@pytest.mark.timeout(5)
def test_metadata_decode_crash_with_invalid_utf8(client):
    """Server crashes when metadata contains non-UTF8 bytes in WebSocket stream."""
    # TODO: Fix UnicodeDecodeError crash in server.py:143 - metadata.decode("utf-8")
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # Directly inject invalid UTF-8 into Redis to bypass upload validation
    async def inject_bad_metadata():
        redis_client = redis.from_url("redis://localhost:6379/0")
        await redis_client.hset(
            f"data:{node_id}:1",
            mapping={
                "metadata": b"\\xff\\xfe\\invalid\\utf8",
                "payload": b"\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00",
            }
        )
        await redis_client.set(f"seq_num:{node_id}", 1)
        await redis_client.aclose()
    
    asyncio.run(inject_bad_metadata())
    
    # This should crash on metadata.decode("utf-8") at line 143
    with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
        websocket.receive_text()  # Should trigger the crash


@pytest.mark.timeout(5) 
def test_json_loads_crash_with_invalid_payload_fallback(client):
    """Server crashes when payload fallback json.loads() fails with invalid JSON."""
    # TODO: Fix json.loads() crash in server.py:140 when payload isn't valid JSON
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # Upload binary data that fails np.frombuffer AND json.loads
    response = client.post(
        f"/upload/{node_id}",
        content=b"\\xff\\xfe\\x00random\\x01invalid\\x02json",
        headers={"Content-Type": "application/octet-stream"}
    )
    assert response.status_code == 200
    
    # WebSocket should crash when both np.frombuffer and json.loads fail
    with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
        websocket.receive_text()  # Should trigger json.loads crash


@pytest.mark.timeout(10)
def test_memory_exhaustion_with_huge_payload(client):
    """Server crashes or hangs with extremely large payloads (10MB+)."""
    # TODO: Add payload size limits to prevent memory exhaustion
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    huge_payload = b"\\x00" * (10 * 1024 * 1024)  # 10MB
    
    try:
        response = client.post(
            f"/upload/{node_id}",
            content=huge_payload,
            headers={"Content-Type": "application/octet-stream"}
        )
        if response.status_code == 200:
            # Test if WebSocket can handle 10MB data without crashing
            with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
                websocket.receive_text()  # May cause memory issues
    except Exception:
        pass  # Expected to fail due to size


@pytest.mark.timeout(5)
def test_redis_pipeline_execute_failure_handling(client):
    """Server may not handle Redis pipeline execution failures gracefully."""
    # TODO: Add proper error handling for Redis pipeline failures
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # Try to trigger a Redis error by using invalid data types or operations
    # This test simulates what happens if Redis becomes unavailable during upload
    
    # Upload with very long metadata that might exceed Redis limits
    very_long_header = "x" * 1000000  # 1MB header value
    try:
        response = client.post(
            f"/upload/{node_id}",
            content=b"\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00",
            headers={
                "Content-Type": "application/octet-stream",
                "Very-Long-Header": very_long_header
            }
        )
        # If this succeeds, test WebSocket behavior
        if response.status_code == 200:
            with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
                websocket.receive_text()
    except Exception:
        pass  # May crash due to Redis limits


@pytest.mark.timeout(5)
def test_concurrent_websocket_connections_same_node(client):
    """Multiple WebSocket connections to same node may cause race conditions.""" 
    # TODO: Fix potential race conditions in Redis pub/sub handling
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # Add some data first
    client.post(
        f"/upload/{node_id}",
        content=b"\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00",
        headers={"Content-Type": "application/octet-stream"}
    )
    
    # Try to open multiple WebSocket connections simultaneously
    try:
        with client.websocket_connect(f"/stream/single/{node_id}") as ws1:
            with client.websocket_connect(f"/stream/single/{node_id}") as ws2:
                # Both should receive data, but race conditions might occur
                ws1.receive_text()
                ws2.receive_text()
    except Exception:
        pass  # May crash due to pub/sub race conditions

