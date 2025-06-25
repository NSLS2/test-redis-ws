import json
import numpy as np
import pytest
import asyncio
import redis.asyncio as redis
from httpx_ws import aconnect_ws


async def create_node_with_id(client, node_id):
    """Helper to create a node with a specific ID."""
    # Set the sequence number for this node_id to 0
    redis_client = redis.from_url("redis://localhost:6379/0")
    await redis_client.setnx(f"seq_num:{node_id}", 0)
    await redis_client.aclose()
    return node_id


async def write_data(client, node_id, data_arrays):
    """Helper to write multiple data arrays sequentially."""
    for data in data_arrays:
        await client.post(
            f"/upload/{node_id}",
            content=data.tobytes(),
            headers={"Content-Type": "application/octet-stream"}
        )


async def collect_messages(websocket_url, client, count, timeout=0.2):
    """Helper to collect messages from WebSocket."""
    messages = []
    websocket = None
    try:
        async with aconnect_ws(websocket_url, client) as ws:
            websocket = ws
            for _ in range(count):
                try:
                    message = await asyncio.wait_for(websocket.receive_text(), timeout=timeout)
                    messages.append(json.loads(message))
                except asyncio.TimeoutError:
                    break  # Stop trying if we timeout on a message
    except Exception:
        pass
    finally:
        # Ensure WebSocket is properly closed
        try:
            if websocket and not websocket.closed:
                await websocket.close()
        except Exception:
            pass
    return messages


def verify_messages(messages, expected_sequences, expected_payloads):
    """Helper to verify message sequences and payloads."""
    assert len(messages) == len(expected_sequences)
    for i, (seq, payload) in enumerate(zip(expected_sequences, expected_payloads)):
        assert messages[i]["sequence"] == seq
        assert messages[i]["payload"] == payload


@pytest.mark.asyncio
async def test_subscribe_immediately_after_creation(test_client):
    """Test subscribing immediately after node creation sees all updates."""
    node_id = await create_node_with_id(test_client, 1001)
    
    try:
        # Start listener immediately
        listener_task = asyncio.create_task(
            collect_messages(f"/stream/single/{node_id}", test_client, 2)
        )
        
        # Small delay to ensure WebSocket connection is established
        await asyncio.sleep(0.01)
        
        # Write data
        data_arrays = [np.array([1.0, 2.0, 3.0]), np.array([4.0, 5.0, 6.0])]
        await write_data(test_client, node_id, data_arrays)
        
        # Verify results with timeout
        try:
            messages = await asyncio.wait_for(listener_task, timeout=2.0)
            verify_messages(messages, [1, 2], [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        except asyncio.TimeoutError:
            listener_task.cancel()
            raise
    finally:
        # Cleanup
        await test_client.delete(f"/upload/{node_id}")


@pytest.mark.asyncio
async def test_subscribe_after_first_update(test_client):
    """Test client that subscribes after first update sees remaining updates."""
    node_id = await create_node_with_id(test_client, 1002)
    
    try:
        # Write first data before subscribing
        await write_data(test_client, node_id, [np.array([1.0, 2.0, 3.0])])
        
        # Small delay to ensure first write is processed
        await asyncio.sleep(0.01)
        
        # Start listener (misses first message)
        listener_task = asyncio.create_task(
            collect_messages(f"/stream/single/{node_id}", test_client, 2)
        )
        
        # Small delay to ensure WebSocket connection is established
        await asyncio.sleep(0.01)
        
        # Write remaining data
        data_arrays = [np.array([4.0, 5.0, 6.0]), np.array([7.0, 8.0, 9.0])]
        await write_data(test_client, node_id, data_arrays)
        
        # Verify results (should only see messages 2 and 3)
        try:
            messages = await asyncio.wait_for(listener_task, timeout=2.0)
            verify_messages(messages, [2, 3], [[4.0, 5.0, 6.0], [7.0, 8.0, 9.0]])
        except asyncio.TimeoutError:
            listener_task.cancel()
            raise
    finally:
        await test_client.delete(f"/upload/{node_id}")


@pytest.mark.asyncio
async def test_subscribe_from_beginning(test_client):
    """Test client that subscribes after updates but requests from beginning."""
    node_id = await create_node_with_id(test_client, 1003)
    
    try:
        # Write initial data
        initial_data = [np.array([1.0, 2.0, 3.0]), np.array([4.0, 5.0, 6.0])]
        await write_data(test_client, node_id, initial_data)
        
        # Start listener with replay from beginning
        listener_task = asyncio.create_task(
            collect_messages(f"/stream/single/{node_id}?seq_num=1", test_client, 3)
        )
        
        # Write additional data
        await write_data(test_client, node_id, [np.array([7.0, 8.0, 9.0])])
        
        # Verify results (should see all 3 messages)
        try:
            messages = await asyncio.wait_for(listener_task, timeout=2.0)
            expected_payloads = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]]
            verify_messages(messages, [1, 2, 3], expected_payloads)
        except asyncio.TimeoutError:
            listener_task.cancel()
            raise
    finally:
        await test_client.delete(f"/upload/{node_id}")


@pytest.mark.asyncio
async def test_multiple_subscribers_different_timing(test_client):
    """Test multiple clients subscribing at different times."""
    node_id = await create_node_with_id(test_client, 1004)
    
    try:
        # Start early subscriber
        early_task = asyncio.create_task(
            collect_messages(f"/stream/single/{node_id}", test_client, 4)
        )
        
        # Write first 2 messages
        first_batch = [np.array([1.0, 2.0, 3.0]), np.array([2.0, 3.0, 4.0])]
        await write_data(test_client, node_id, first_batch)
        
        # Start late subscriber (after first 2 messages)
        late_task = asyncio.create_task(
            collect_messages(f"/stream/single/{node_id}", test_client, 2)
        )
        
        # Write remaining messages
        second_batch = [np.array([3.0, 4.0, 5.0]), np.array([4.0, 5.0, 6.0])]
        await write_data(test_client, node_id, second_batch)
        
        # Start replay subscriber
        replay_task = asyncio.create_task(
            collect_messages(f"/stream/single/{node_id}?seq_num=1", test_client, 4)
        )
        
        # Wait for all results with timeouts
        try:
            early_messages = await asyncio.wait_for(early_task, timeout=2.0)
            late_messages = await asyncio.wait_for(late_task, timeout=2.0)
            replay_messages = await asyncio.wait_for(replay_task, timeout=2.0)
        except asyncio.TimeoutError:
            # Cancel any hanging tasks
            for task in [early_task, late_task, replay_task]:
                if not task.done():
                    task.cancel()
            raise
        
        # Verify early subscriber got all messages
        expected_payloads = [[1.0, 2.0, 3.0], [2.0, 3.0, 4.0], [3.0, 4.0, 5.0], [4.0, 5.0, 6.0]]
        verify_messages(early_messages, [1, 2, 3, 4], expected_payloads)
        
        # Verify late subscriber got only messages 3 and 4
        verify_messages(late_messages, [3, 4], expected_payloads[2:])
        
        # Verify replay subscriber got all messages
        verify_messages(replay_messages, [1, 2, 3, 4], expected_payloads)
    finally:
        await test_client.delete(f"/upload/{node_id}")
        await asyncio.sleep(0.05)