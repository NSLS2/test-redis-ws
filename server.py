import redis.asyncio as redis
import json
from json import JSONDecodeError
import numpy as np
import uvicorn
from pydantic_settings import BaseSettings
from fastapi import FastAPI, WebSocket, Request, WebSocketDisconnect, HTTPException
from datetime import datetime
import msgpack
import asyncio
from typing import Optional
import socket
from contextlib import asynccontextmanager


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"
    ttl: int = 60 * 60  # 1 hour
    # Resource limits to prevent memory exhaustion and DoS attacks
    # Fix for: test_large_data_resource.py::test_large_data_resource_limits (payload/header limits only)
    max_payload_size: int = 16 * 1024 * 1024  # 16MB max payload
    max_header_size: int = 8 * 1024  # 8KB max individual header value
    max_websocket_frame_size: int = 1024 * 1024  # 1MB max WebSocket frame


def build_app(settings: Settings):
    redis_client = redis.from_url(settings.redis_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        # Shutdown - close Redis connection
        await redis_client.aclose()

    app = FastAPI(lifespan=lifespan)

    @app.middleware("http")
    async def add_server_header(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Server-Host"] = socket.gethostname()
        return response

    @app.post("/upload")
    async def create():
        "Declare a new dataset."

        # Generate a rnadom node_id.
        # (In Tiled, PostgreSQL will give us a unique ID.)
        node_id = np.random.randint(1_000_000)
        # Allocate a counter for this node_id.
        await redis_client.setnx(f"seq_num:{node_id}", 0)
        return {"node_id": node_id}

    @app.delete("/upload/{node_id}", status_code=204)
    async def close(node_id):
        "Declare that a dataset is done streaming."

        await redis_client.delete(f"seq_num:{node_id}")
        # TODO: Shorten TTL on all extant data for this node.
        return None

    @app.post("/upload/{node_id}")
    async def append(node_id, request: Request):
        "Append data to a dataset."

        # get data from request body with size validation
        binary_data = await request.body()
        
        # Check payload size limit to prevent memory exhaustion
        # Fix for: test_large_data_resource.py::test_large_data_resource_limits (payload test)
        if len(binary_data) > settings.max_payload_size:
            raise HTTPException(status_code=413, detail="Payload too large")
        
        headers = request.headers
        
        # Check header sizes to prevent header-based DoS attacks
        # Fix for: test_large_data_resource.py::test_large_data_resource_limits (header test)
        for name, value in headers.items():
            if len(value) > settings.max_header_size:
                raise HTTPException(status_code=431, detail=f"Header '{name}' too large")
        metadata = {
            "timestamp": datetime.now().isoformat(),
        }
        metadata.setdefault("Content-Type", headers.get("Content-Type"))

        # Increment the counter for this node.
        seq_num = await redis_client.incr(f"seq_num:{node_id}")

        # Cache data in Redis with a TTL, and publish
        # a notification about it.
        pipeline = redis_client.pipeline()
        pipeline.hset(
            f"data:{node_id}:{seq_num}",
            mapping={
                "metadata": json.dumps(metadata).encode("utf-8"),
                "payload": binary_data,  # Raw binary bytes
            },
        )
        pipeline.expire(f"data:{node_id}:{seq_num}", settings.ttl)
        pipeline.publish(f"notify:{node_id}", seq_num)
        await pipeline.execute()

    # TODO: Implement two-way communication with subscribe, unsubscribe, flow control.
    #   @app.websocket("/stream/many")

    @app.post("/close/{node_id}")
    async def close_connection(node_id: str, request: Request):
        # Parse JSON body with error handling to prevent server crashes
        # Fix for: test_json_parsing.py::test_json_parsing_errors_in_close_endpoint
        try:
            body = await request.json()
        except JSONDecodeError:
            raise HTTPException(
                status_code=400, 
                detail="Request body contains invalid JSON syntax"
            )
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail="Request body must be valid JSON"
            )
        
        headers = request.headers

        reason = body.get("reason", None)

        metadata = {"timestamp": datetime.now().isoformat(), "reason": reason}
        metadata.setdefault("Content-Type", headers.get("Content-Type"))
        # Increment the counter for this node.
        seq_num = await redis_client.incr(f"seq_num:{node_id}")

        # Cache data in Redis with a TTL, and publish
        # a notification about it.
        pipeline = redis_client.pipeline()
        pipeline.hset(
            f"data:{node_id}:{seq_num}",
            mapping={
                "metadata": json.dumps(metadata).encode("utf-8"),
                "payload": json.dumps(None).encode("utf-8"),
            },
        )
        pipeline.expire(f"data:{node_id}:{seq_num}", settings.ttl)
        pipeline.publish(f"notify:{node_id}", seq_num)
        await pipeline.execute()

        return {
            "status": f"Connection for node {node_id} is now closed.",
            "reason": reason,
        }

    @app.websocket("/stream/single/{node_id}")  # one-way communcation
    async def websocket_endpoint(
        websocket: WebSocket,
        node_id: str,
        envelope_format: str = "json",
        seq_num: Optional[int] = None,
    ):
        await websocket.accept(
            headers=[(b"x-server-host", socket.gethostname().encode())]
        )
        end_stream = asyncio.Event()

        async def stream_data(seq_num):
            key = f"data:{node_id}:{seq_num}"
            payload, metadata = await redis_client.hmget(key, "payload", "metadata")
            if payload is None and metadata is None:
                return
            try:
                payload = np.frombuffer(payload, dtype=np.float64).tolist()
            except Exception:
                payload = json.loads(payload)
            data = {
                "sequence": seq_num,
                "metadata": metadata.decode("utf-8"),
                "payload": payload,
                "server_host": socket.gethostname(),
            }
            
            # Check WebSocket frame size to prevent client hangs and memory issues
            # Proactive fix: prevents oversized frames that could hang clients (not currently tested)
            if envelope_format == "msgpack":
                frame_data = msgpack.packb(data)
                if len(frame_data) > settings.max_websocket_frame_size:
                    error_data = {"error": "Frame too large"}
                    await websocket.send_bytes(msgpack.packb(error_data))
                    return
                await websocket.send_bytes(frame_data)
            else:
                frame_data = json.dumps(data)
                if len(frame_data) > settings.max_websocket_frame_size:
                    error_data = {"error": "Frame too large"}
                    await websocket.send_text(json.dumps(error_data))
                    return
                await websocket.send_text(frame_data)
            if payload is None and metadata is not None:
                # This means that the stream is closed by the producer
                end_stream.set()

        # Setup buffer
        stream_buffer = asyncio.Queue()

        async def buffer_live_events():
            pubsub = redis_client.pubsub()
            try:
                await pubsub.subscribe(f"notify:{node_id}")
                async for message in pubsub.listen():
                    if message.get("type") == "message":
                        try:
                            live_seq = int(message["data"])
                            await stream_buffer.put(live_seq)
                        except Exception as e:
                            print(f"Error parsing live message: {e}")
                            break  # Exit loop on error
            except asyncio.CancelledError:
                # Task was cancelled by live_task.cancel() - don't re-raise, just clean up
                pass
            except Exception as e:
                print(f"Live subscription error: {e}")
            finally:
                await pubsub.unsubscribe(f"notify:{node_id}")
                await pubsub.aclose()

        live_task = asyncio.create_task(buffer_live_events())

        if seq_num is not None:
            current_seq = await redis_client.get(f"seq_num:{node_id}")
            current_seq = int(current_seq) if current_seq is not None else 0
            # Replay old data
            for s in range(seq_num, current_seq + 1):
                await stream_data(s)
        # New data
        try:
            while not end_stream.is_set():
                try:
                    async with asyncio.timeout(1.0):
                        live_seq = await stream_buffer.get()
                except asyncio.TimeoutError:
                    # No data for 1 second - continue waiting
                    # Client disconnect will be detected on next send operation
                    continue
                else:
                    await stream_data(live_seq)
            else:
                await websocket.close(code=1000, reason="Producer ended stream")
        except WebSocketDisconnect:
            print(f"Client disconnected from node {node_id}")
        finally:
            # Properly cancel and wait for the live task to cleanup with timeout
            live_task.cancel()
            try:
                # Wait for task to finish cleanup (unsubscribe, close pubsub connection)
                # before allowing WebSocket handler to exit
                await asyncio.wait_for(live_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass  # Task cleanup completed or timed out

    @app.get("/stream/live")
    async def list_live_streams():
        nodes = await redis_client.keys("seq_num:*")
        return [node.decode("utf-8").split(":")[1] for node in nodes]

    return app


settings = Settings()
app = build_app(settings)

if __name__ == "__main__":
    uvicorn.run(app)
