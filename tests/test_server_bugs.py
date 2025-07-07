"""
Tests designed to expose bugs, crashes, and incorrect behavior in the server.
"""
import asyncio
import json
import socket
import struct
import pytest
import redis.asyncio as redis


def test_malformed_json_in_close_endpoint(client):
    """Server should handle malformed JSON in /close endpoint gracefully."""
    # TODO: Fix JSONDecodeError crash in server.py:91 - add proper error handling
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # This should not crash - server should handle malformed JSON gracefully
    response = client.post(
        f"/close/{node_id}",
        content=b"invalid json {{{",
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400  # Should return bad request, not crash


def test_missing_json_body_in_close_endpoint(client):
    """Server should handle missing JSON body in /close endpoint gracefully."""
    # TODO: Fix JSONDecodeError crash in server.py:91 - add proper error handling
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # This should not crash - server should handle missing JSON body gracefully
    response = client.post(f"/close/{node_id}")
    assert response.status_code == 400  # Should return bad request, not crash


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
    
    # Test WebSocket behavior with invalid binary data - should handle gracefully
    with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
        # This should not crash - server should handle invalid data gracefully
        msg_text = websocket.receive_text()
        msg = json.loads(msg_text)
        # Should successfully convert invalid data using json.loads fallback
        assert "payload" in msg


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
    
    # Server should handle large payloads gracefully with proper limits
    response = client.post(
        f"/upload/{node_id}",
        content=huge_payload,
        headers={"Content-Type": "application/octet-stream"}
    )
    # Should either accept with size limit or reject with 413 Payload Too Large
    assert response.status_code in [200, 413]
    
    if response.status_code == 200:
        # If accepted, WebSocket should handle large data without hanging
        with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
            msg_text = websocket.receive_text()
            assert len(msg_text) > 0  # Should receive data without hanging


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
    # Server should handle large headers gracefully
    response = client.post(
        f"/upload/{node_id}",
        content=b"\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00",
        headers={
            "Content-Type": "application/octet-stream",
            "Very-Long-Header": very_long_header
        }
    )
    # Should either accept or reject with proper error code
    assert response.status_code in [200, 413, 431]  # 431 = Request Header Fields Too Large
    
    if response.status_code == 200:
        # If accepted, WebSocket should work without hanging
        with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
            msg_text = websocket.receive_text()
            assert len(msg_text) > 0


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
def test_redis_connection_loss_during_websocket(client):
    """Server crashes or hangs when Redis becomes unavailable during WebSocket stream."""
    # TODO: Add proper error handling for Redis connection failures during streaming
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # Add initial data
    client.post(
        f"/upload/{node_id}",
        content=b"\x00\x00\x00\x00\x00\x00\x00\x00",
        headers={"Content-Type": "application/octet-stream"}
    )
    
    # Start WebSocket, then simulate Redis failure by corrupting Redis data
    async def corrupt_redis_data():
        redis_client = redis.from_url("redis://localhost:6379/0")
        # Corrupt the seq_num key to simulate Redis failure
        await redis_client.set(f"seq_num:{node_id}", "invalid_number")
        # Corrupt notification data
        await redis_client.publish(f"notify:{node_id}", "invalid_seq")
        await redis_client.aclose()
    
    with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
        websocket.receive_text()  # Get initial message
        asyncio.run(corrupt_redis_data())
        # Try to trigger another upload to cause Redis errors
        client.post(
            f"/upload/{node_id}",
            content=b"\x01\x00\x00\x00\x00\x00\x00\x00",
            headers={"Content-Type": "application/octet-stream"}
        )
        # WebSocket should handle Redis errors gracefully but likely hangs


@pytest.mark.timeout(5)
def test_redis_key_collision_with_concurrent_uploads(client):
    """Race condition when multiple uploads use same node_id with Redis operations."""
    # TODO: Fix race conditions in Redis pipeline operations for same node_id
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # Manually inject data to simulate concurrent access to same keys
    async def create_key_collision():
        redis_client = redis.from_url("redis://localhost:6379/0")
        # Simulate race condition by setting conflicting seq_num values
        await redis_client.set(f"seq_num:{node_id}", 10)  # Set high value
        # Add data for seq 5 while seq_num is 10 - inconsistent state
        await redis_client.hset(
            f"data:{node_id}:5",
            mapping={
                "metadata": b'{"timestamp": "test"}',
                "payload": b"\x00\x00\x00\x00\x00\x00\x00\x00",
            }
        )
        await redis_client.aclose()
    
    asyncio.run(create_key_collision())
    
    # Now try normal upload - should cause seq_num inconsistency
    client.post(
        f"/upload/{node_id}",
        content=b"\x01\x00\x00\x00\x00\x00\x00\x00",
        headers={"Content-Type": "application/octet-stream"}
    )
    
    # WebSocket may hang or crash due to inconsistent Redis state
    with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
        websocket.receive_text()


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
def test_websocket_send_after_close(client):
    """Server may crash when trying to send data after WebSocket client disconnects."""
    # TODO: Add proper connection state checking before WebSocket sends
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # Create a scenario where data arrives after WebSocket closes
    async def trigger_post_close_send():
        redis_client = redis.from_url("redis://localhost:6379/0")
        # Wait a moment then publish data that will try to send to closed WebSocket
        await asyncio.sleep(0.1)
        await redis_client.incr(f"seq_num:{node_id}")
        await redis_client.hset(
            f"data:{node_id}:1",
            mapping={
                "metadata": b'{"timestamp": "test"}',
                "payload": b"\x00\x00\x00\x00\x00\x00\x00\x00",
            }
        )
        await redis_client.publish(f"notify:{node_id}", 1)
        await redis_client.aclose()
    
    # Start WebSocket and immediately close it, then trigger data
    with client.websocket_connect(f"/stream/single/{node_id}"):
        pass  # WebSocket closes immediately
    
    # This should trigger a send attempt to a closed WebSocket
    asyncio.run(trigger_post_close_send())


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
def test_websocket_frame_size_limits(client):
    """Server hangs or crashes with extremely large WebSocket frames."""
    # TODO: Add frame size limits to prevent buffer overflow attacks
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # Create huge metadata that will result in massive WebSocket frame
    async def inject_huge_frame_data():
        redis_client = redis.from_url("redis://localhost:6379/0")
        # Create 5MB metadata that will be sent as single WebSocket frame
        huge_metadata = json.dumps({"data": "x" * (5 * 1024 * 1024)})
        await redis_client.hset(
            f"data:{node_id}:1",
            mapping={
                "metadata": huge_metadata.encode("utf-8"),
                "payload": b"\x00\x00\x00\x00\x00\x00\x00\x00",
            }
        )
        await redis_client.set(f"seq_num:{node_id}", 1)
        await redis_client.aclose()
    
    asyncio.run(inject_huge_frame_data())
    
    # WebSocket should handle huge frames gracefully but may hang/crash
    with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
        websocket.receive_text()  # May cause buffer overflow or hang


@pytest.mark.timeout(5)
def test_numpy_dtype_overflow_with_extreme_values(client):
    """Server crashes when np.frombuffer encounters values that overflow float64."""
    # TODO: Add bounds checking for float64 conversion in server.py:138
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # Create binary data with extreme values that might overflow
    # Pack extreme float64 values that are at the edge of representation
    extreme_values = [
        float('inf'),        # Positive infinity
        float('-inf'),       # Negative infinity
        1.7976931348623157e+308,  # Near float64 max
        -1.7976931348623157e+308, # Near float64 min
    ]
    
    # Pack as binary data
    extreme_binary = b''.join(struct.pack('d', val) for val in extreme_values)
    
    response = client.post(
        f"/upload/{node_id}",
        content=extreme_binary,
        headers={"Content-Type": "application/octet-stream"}
    )
    assert response.status_code == 200
    
    # np.frombuffer might crash or produce NaN/Inf that breaks JSON serialization
    with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
        websocket.receive_text()  # May crash on infinite values in JSON


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


