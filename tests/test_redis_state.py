"""
Tests for Redis state corruption and error handling bugs.
"""
import asyncio
import pytest
import redis.asyncio as redis


@pytest.mark.timeout(5)
def test_redis_state_corruption_handling(client):
    """Server should handle Redis state corruption and connection issues gracefully."""
    # TODO: Add Redis error handling and state validation
    
    # Test 1: Redis connection loss during WebSocket streaming
    response = client.post("/upload")
    assert response.status_code == 200
    node_id1 = response.json()["node_id"]
    
    client.post(
        f"/upload/{node_id1}",
        content=b"\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00",
        headers={"Content-Type": "application/octet-stream"}
    )
    
    async def corrupt_redis_data():
        redis_client = redis.from_url("redis://localhost:6379/0")
        await redis_client.set(f"seq_num:{node_id1}", "invalid_number")  # Corrupt seq_num
        await redis_client.publish(f"notify:{node_id1}", "invalid_seq")  # Corrupt notification
        await redis_client.aclose()
    
    with client.websocket_connect(f"/stream/single/{node_id1}") as websocket:
        websocket.receive_text()  # Get initial message
        asyncio.run(corrupt_redis_data())
        
        # Try to trigger another upload to cause Redis errors
        client.post(
            f"/upload/{node_id1}",
            content=b"\\x01\\x00\\x00\\x00\\x00\\x00\\x00\\x00",
            headers={"Content-Type": "application/octet-stream"}
        )
        # Should handle Redis errors gracefully
    
    # Test 2: Redis key collision with inconsistent seq_num values
    response = client.post("/upload")
    assert response.status_code == 200
    node_id2 = response.json()["node_id"]
    
    async def create_key_collision():
        redis_client = redis.from_url("redis://localhost:6379/0")
        await redis_client.set(f"seq_num:{node_id2}", 10)  # Set high seq_num
        # Add data for seq 5 while seq_num is 10 - creates inconsistency
        await redis_client.hset(
            f"data:{node_id2}:5",
            mapping={
                "metadata": b'{"timestamp": "test"}',
                "payload": b"\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00",
            }
        )
        await redis_client.aclose()
    
    asyncio.run(create_key_collision())
    
    # Normal upload should handle seq_num inconsistency
    client.post(
        f"/upload/{node_id2}",
        content=b"\\x01\\x00\\x00\\x00\\x00\\x00\\x00\\x00",
        headers={"Content-Type": "application/octet-stream"}
    )
    
    with client.websocket_connect(f"/stream/single/{node_id2}") as websocket:
        msg_text = websocket.receive_text()  # Should handle inconsistent Redis state
        assert len(msg_text) > 0