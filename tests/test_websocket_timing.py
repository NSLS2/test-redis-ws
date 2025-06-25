import json
import numpy as np
import pytest
import asyncio
import redis.asyncio as redis
from httpx_ws import aconnect_ws
import httpx
from httpx_ws.transport import ASGIWebSocketTransport
import time


async def create_node_with_id(client, base_id):
    """Helper to create a node with a unique ID based on timestamp."""
    # Create truly unique node_id using base_id and timestamp
    unique_id = int(f"{base_id}{int(time.time() * 1000) % 10000}")
    
    # Set the sequence number for this node_id to 0
    redis_client = redis.from_url("redis://localhost:6379/0")
    await redis_client.setnx(f"seq_num:{unique_id}", 0)
    await redis_client.aclose()
    return unique_id


async def write_data(client, node_id, data_arrays):
    """Helper to write multiple data arrays sequentially."""
    for data in data_arrays:
        await client.post(
            f"/upload/{node_id}",
            content=data.tobytes(),
            headers={"Content-Type": "application/octet-stream"}
        )


async def write_data_sequential(client, node_id, data_arrays):
    """Helper to write multiple data arrays sequentially with small delays."""
    for data in data_arrays:
        await client.post(
            f"/upload/{node_id}",
            content=data.tobytes(),
            headers={"Content-Type": "application/octet-stream"}
        )
        await asyncio.sleep(0.01)  # Small delay between writes


async def collect_messages_sequential(websocket_url, client, count, timeout=1.0):
    """Helper to collect messages from WebSocket sequentially."""
    messages = []
    try:
        async with aconnect_ws(websocket_url, client) as ws:
            for _ in range(count):
                try:
                    message = await asyncio.wait_for(ws.receive_text(), timeout=timeout)
                    messages.append(json.loads(message))
                except asyncio.TimeoutError:
                    break  # Stop trying if we timeout on a message
    except Exception:
        pass  # Let the context manager handle cleanup
    return messages


def verify_messages(messages, expected_sequences, expected_payloads):
    """Helper to verify message sequences and payloads."""
    assert len(messages) == len(expected_sequences)
    for i, (seq, payload) in enumerate(zip(expected_sequences, expected_payloads)):
        assert messages[i]["sequence"] == seq
        assert messages[i]["payload"] == payload


@pytest.mark.asyncio
async def test_subscribe_immediately_after_creation(app):
    """Test subscribing immediately after node creation sees all updates."""
    transport = ASGIWebSocketTransport(app=app)
    
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        node_id = await create_node_with_id(client, 1001)
        
        try:
            async with asyncio.TaskGroup() as tg:
                # Create listener task
                listener_task = tg.create_task(
                    collect_messages_sequential(f"/stream/single/{node_id}", client, 2)
                )
                
                # Small delay to ensure WebSocket connection is established
                await asyncio.sleep(0.02)
                
                # Write data sequentially
                data_arrays = [np.array([1.0, 2.0, 3.0]), np.array([4.0, 5.0, 6.0])]
                tg.create_task(
                    write_data_sequential(client, node_id, data_arrays)
                )
            
            # Verify results
            verify_messages(listener_task.result(), [1, 2], [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        finally:
            # Cleanup
            await client.delete(f"/upload/{node_id}")


@pytest.mark.asyncio
async def test_subscribe_after_first_update(app):
    """Test client that subscribes after first update sees remaining updates."""
    transport = ASGIWebSocketTransport(app=app)
    
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        node_id = await create_node_with_id(client, 1002)
        
        try:
            # Write first data before subscribing
            await write_data(client, node_id, [np.array([1.0, 2.0, 3.0])])
            
            # Delay to ensure first write is fully processed and published
            await asyncio.sleep(0.05)
            
            # Start listener and writer sequentially
            async with asyncio.TaskGroup() as tg:
                listener_task = tg.create_task(
                    collect_messages_sequential(f"/stream/single/{node_id}", client, 2)
                )
                
                # Delay to ensure WebSocket connection is established
                await asyncio.sleep(0.05)
                
                # Write remaining data
                remaining_data = [np.array([4.0, 5.0, 6.0]), np.array([7.0, 8.0, 9.0])]
                tg.create_task(
                    write_data_sequential(client, node_id, remaining_data)
                )
            
            # Verify results (should only see messages 2 and 3)
            verify_messages(listener_task.result(), [2, 3], [[4.0, 5.0, 6.0], [7.0, 8.0, 9.0]])
        finally:
            await client.delete(f"/upload/{node_id}")


@pytest.mark.asyncio
async def test_subscribe_from_beginning(app):
    """Test client that subscribes after updates but requests from beginning."""
    transport = ASGIWebSocketTransport(app=app)
    
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        node_id = await create_node_with_id(client, 1003)
        
        try:
            # Write initial data
            initial_data = [np.array([1.0, 2.0, 3.0]), np.array([4.0, 5.0, 6.0])]
            await write_data(client, node_id, initial_data)
            
            # Delay to ensure data is written
            await asyncio.sleep(0.05)
            
            # Start listener with replay from beginning and additional writer
            async with asyncio.TaskGroup() as tg:
                listener_task = tg.create_task(
                    collect_messages_sequential(f"/stream/single/{node_id}?seq_num=1", client, 3)
                )
                
                # Delay to establish connection
                await asyncio.sleep(0.05)
                
                # Write additional data
                tg.create_task(
                    write_data_sequential(client, node_id, [np.array([7.0, 8.0, 9.0])])
                )
            
            # Verify results (should see all 3 messages)
            expected_payloads = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]]
            verify_messages(listener_task.result(), [1, 2, 3], expected_payloads)
        finally:
            await client.delete(f"/upload/{node_id}")


@pytest.mark.asyncio
async def test_multiple_subscribers_different_timing(app):
    """Test multiple clients subscribing at different times."""
    transport = ASGIWebSocketTransport(app=app)
    
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        node_id = await create_node_with_id(client, 1004)
        
        try:
            # Sequential execution: early subscriber, write data, late subscriber, more data, replay subscriber
            
            # Phase 1: Start early subscriber and write first batch
            
            async with asyncio.TaskGroup() as tg1:
                early_task = tg1.create_task(
                    collect_messages_sequential(f"/stream/single/{node_id}", client, 4)
                )
                
                await asyncio.sleep(0.05)  # Ensure connection established
                
                # Write first 2 messages
                first_batch = [np.array([1.0, 2.0, 3.0]), np.array([2.0, 3.0, 4.0])]
                tg1.create_task(
                    write_data_sequential(client, node_id, first_batch)
                )
            
            await asyncio.sleep(0.05)  # Delay before late subscriber
            
            # Phase 2: Start late subscriber and write remaining data
            async with asyncio.TaskGroup() as tg2:
                late_task = tg2.create_task(
                    collect_messages_sequential(f"/stream/single/{node_id}", client, 2)
                )
                
                await asyncio.sleep(0.05)  # Ensure connection established
                
                # Write remaining messages
                second_batch = [np.array([3.0, 4.0, 5.0]), np.array([4.0, 5.0, 6.0])]
                tg2.create_task(
                    write_data_sequential(client, node_id, second_batch)
                )
            
            # Phase 3: Start replay subscriber
            async with asyncio.TaskGroup() as tg3:
                replay_task = tg3.create_task(
                    collect_messages_sequential(f"/stream/single/{node_id}?seq_num=1", client, 4)
                )
            
            # Verify all results
            expected_payloads = [[1.0, 2.0, 3.0], [2.0, 3.0, 4.0], [3.0, 4.0, 5.0], [4.0, 5.0, 6.0]]
            
            # Verify early subscriber got all messages
            verify_messages(early_task.result(), [1, 2, 3, 4], expected_payloads)
            
            # Verify late subscriber got only messages 3 and 4
            verify_messages(late_task.result(), [3, 4], expected_payloads[2:])
            
            # Verify replay subscriber got all messages
            verify_messages(replay_task.result(), [1, 2, 3, 4], expected_payloads)
        finally:
            await client.delete(f"/upload/{node_id}")