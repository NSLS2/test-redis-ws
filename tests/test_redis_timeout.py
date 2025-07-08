import time
import pytest
import redis.asyncio as redis


def test_redis_command_with_slow_operation():
    """Test that Redis operations timeout when they take too long."""
    import asyncio
    from server import Settings
    
    # Create Redis client with timeout configuration
    settings = Settings(redis_url="redis://localhost:6379/0", ttl=60 * 60)
    redis_client = redis.from_url(
        settings.redis_url,
        # Operations will hang indefinitely without this timeout.
        socket_timeout=1.0,  # 1 second timeout
        retry_on_timeout=False
    )
    
    async def run_slow_operation():
        # Use a Lua script that busy-waits for 3 seconds (longer than timeout)
        slow_script = """
        local start_time = tonumber(redis.call('TIME')[1])
        local end_time = start_time + 3
        
        while tonumber(redis.call('TIME')[1]) < end_time do
            -- busy wait
        end
        
        return "done"
        """
        
        # This should timeout because the script takes 3 seconds but timeout is 1s
        result = await redis_client.eval(slow_script, 0)
        return result
    
    start_time = time.time()
    
    # This should timeout, not complete successfully
    with pytest.raises((redis.TimeoutError)):
        asyncio.run(run_slow_operation())
    
    elapsed_time = time.time() - start_time
    
    # Should timeout within a reasonable time (much less than 3 seconds)
    assert elapsed_time < 2.0, f"Redis operation took too long: {elapsed_time} seconds"
    
    # Clean up
    try:
        asyncio.run(redis_client.aclose())
    except Exception:
        pass
