"""
Tests for large data handling and resource limit bugs.
"""
import asyncio
import json
import pytest
import redis.asyncio as redis


@pytest.mark.timeout(10)
def test_large_data_resource_limits(client):
    """Server should handle large data with proper resource limits."""
    # TODO: Add payload/header/frame size limits to prevent memory exhaustion
    
    # Test 1: Huge payload (10MB) - should have size limits
    response = client.post("/upload")
    assert response.status_code == 200
    node_id1 = response.json()["node_id"]
    
    huge_payload = b"\\x00" * (10 * 1024 * 1024)  # 10MB
    response = client.post(
        f"/upload/{node_id1}",
        content=huge_payload,
        headers={"Content-Type": "application/octet-stream"}
    )
    assert response.status_code in [200, 413]  # Should either accept or reject with Payload Too Large
    
    if response.status_code == 200:
        with client.websocket_connect(f"/stream/single/{node_id1}") as websocket:
            msg_text = websocket.receive_text()
            assert len(msg_text) > 0  # Should handle without hanging
    
    # Test 2: Very long headers (1MB) - should have header size limits
    response = client.post("/upload")
    assert response.status_code == 200
    node_id2 = response.json()["node_id"]
    
    very_long_header = "x" * 1000000  # 1MB header
    response = client.post(
        f"/upload/{node_id2}",
        content=b"\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00",
        headers={
            "Content-Type": "application/octet-stream",
            "Very-Long-Header": very_long_header
        }
    )
    assert response.status_code in [200, 413, 431]  # Should handle or reject properly
    
    if response.status_code == 200:
        with client.websocket_connect(f"/stream/single/{node_id2}") as websocket:
            msg_text = websocket.receive_text()
            assert len(msg_text) > 0
    
    # Test 3: Huge WebSocket frames (5MB metadata) - should have frame size limits
    response = client.post("/upload")
    assert response.status_code == 200
    node_id3 = response.json()["node_id"]
    
    async def inject_huge_frame_data():
        redis_client = redis.from_url("redis://localhost:6379/0")
        huge_metadata = json.dumps({"data": "x" * (5 * 1024 * 1024)})  # 5MB metadata
        await redis_client.hset(
            f"data:{node_id3}:1",
            mapping={
                "metadata": huge_metadata.encode("utf-8"),
                "payload": b"\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00",
            }
        )
        await redis_client.set(f"seq_num:{node_id3}", 1)
        await redis_client.aclose()
    
    asyncio.run(inject_huge_frame_data())
    
    with client.websocket_connect(f"/stream/single/{node_id3}") as websocket:
        msg_text = websocket.receive_text()  # Should handle huge frames without hanging
        assert len(msg_text) > 0