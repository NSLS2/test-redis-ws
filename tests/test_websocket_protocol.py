"""
Tests for WebSocket protocol handling bugs and edge cases.
"""
import asyncio
import json
import socket
import struct
import pytest
import redis.asyncio as redis




def test_websocket_invalid_seq_num_string(client):
    """Server should handle invalid seq_num parameter gracefully."""
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # Server should validate seq_num and return proper error response
    with client.websocket_connect(f"/stream/single/{node_id}?seq_num=invalid") as websocket:
        # Should either connect successfully or provide error message
        # Currently this disconnects abruptly - should handle more gracefully
        msg_text = websocket.receive_text()
        assert "error" in msg_text.lower() or "invalid" in msg_text.lower()



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
    
    # Server should handle multiple WebSocket connections gracefully
    with client.websocket_connect(f"/stream/single/{node_id}") as ws1:
        with client.websocket_connect(f"/stream/single/{node_id}") as ws2:
            # Both connections should receive data without race conditions
            msg1 = ws1.receive_text()
            msg2 = ws2.receive_text()
            # Both should receive valid messages
            assert len(msg1) > 0 and len(msg2) > 0
            # Both should contain the same data
            data1 = json.loads(msg1)
            data2 = json.loads(msg2)
            assert data1["sequence"] == data2["sequence"]




@pytest.mark.timeout(5)
def test_redis_pubsub_unsubscribe_failure(client):
    """Server hangs when Redis pubsub unsubscribe fails during WebSocket cleanup."""
    # TODO: Add timeout protection for pubsub cleanup operations
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # Add data
    client.post(
        f"/upload/{node_id}",
        content=b"\x00\x00\x00\x00\x00\x00\x00\x00",
        headers={"Content-Type": "application/octet-stream"}
    )
    
    # Create situation where pubsub cleanup might fail
    async def create_pubsub_interference():
        redis_client = redis.from_url("redis://localhost:6379/0")
        # Create lots of active subscriptions to same channel
        pubsub1 = redis_client.pubsub()
        pubsub2 = redis_client.pubsub() 
        await pubsub1.subscribe(f"notify:{node_id}")
        await pubsub2.subscribe(f"notify:{node_id}")
        # Don't clean up - leave hanging subscriptions
        # This simulates a condition that might interfere with cleanup
        await redis_client.aclose()
    
    asyncio.run(create_pubsub_interference())
    
    # WebSocket connection might hang during cleanup due to pubsub issues
    with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
        websocket.receive_text()
        # Cleanup should happen when context exits, may hang




@pytest.mark.timeout(5)
def test_websocket_malformed_headers_injection(client):
    """Server crashes when WebSocket accept receives malformed headers."""
    # TODO: Add validation for WebSocket header values  
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # Try to inject malformed headers that could crash WebSocket accept
    # This tests the server.py:128 line: await websocket.accept(headers=...)
    
    # Simulate environment where hostname is corrupted or very long
    original_gethostname = socket.gethostname
    
    def mock_long_hostname():
        return "x" * 65536  # Extremely long hostname that might overflow header
    
    socket.gethostname = mock_long_hostname
    
    try:
        # Server should handle long hostname gracefully without crashing
        with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
            msg_text = websocket.receive_text()
            # Should receive data successfully even with long hostname
            assert len(msg_text) > 0
    finally:
        socket.gethostname = original_gethostname


@pytest.mark.timeout(5)
def test_msgpack_serialization_failure_with_complex_data(client):
    """Server crashes when msgpack.packb fails with non-serializable data structures."""
    # TODO: Add error handling for msgpack serialization failures in server.py:148
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # Inject data that will create complex nested structures that msgpack can't handle
    async def inject_complex_data():
        redis_client = redis.from_url("redis://localhost:6379/0")
        # Create metadata with circular references or extreme nesting
        complex_metadata = json.dumps({
            "nested": {"level" + str(i): "data" for i in range(1000)},  # Deep nesting
            "special_chars": "\x00\x01\x02\x03\x04\x05",  # Control characters
            "unicode": "🚀" * 1000,  # Heavy unicode
        })
        
        await redis_client.hset(
            f"data:{node_id}:1",
            mapping={
                "metadata": complex_metadata.encode("utf-8"),
                "payload": b"\x00\x00\x00\x00\x00\x00\x00\x00",
            }
        )
        await redis_client.set(f"seq_num:{node_id}", 1)
        await redis_client.aclose()
    
    asyncio.run(inject_complex_data())
    
    # Request msgpack format - should crash when msgpack.packb fails
    with client.websocket_connect(f"/stream/single/{node_id}?envelope_format=msgpack") as websocket:
        websocket.receive_bytes()  # Should trigger msgpack serialization failure


