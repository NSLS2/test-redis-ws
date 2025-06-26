import redis.asyncio as redis
import json
import numpy as np
import uvicorn
from pydantic_settings import BaseSettings
from fastapi import FastAPI, WebSocket, Request, WebSocketDisconnect
from datetime import datetime
import msgpack
import asyncio
from typing import Optional
import socket
from contextlib import asynccontextmanager


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"
    ttl: int = 60 * 60  # 1 hour


def build_app(settings: Settings):
    redis_client = redis.from_url(settings.redis_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        app.state.redis_client = redis_client
        yield
        # Shutdown
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

        # get data from request body
        binary_data = await request.body()
        headers = request.headers
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
        # Parse the JSON body
        body = await request.json()
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
            if envelope_format == "msgpack":
                data = msgpack.packb(data)
                await websocket.send_bytes(data)
            else:
                await websocket.send_text(json.dumps(data))
            if payload is None and metadata is not None:
                # This means that the stream is closed by the producer
                end_stream.set()

        # Setup buffer
        stream_buffer = asyncio.Queue()

        # Create a separate Redis client for this WebSocket connection
        ws_redis_client = redis.from_url(settings.redis_url)

        async def buffer_live_events():
            pubsub = ws_redis_client.pubsub()
            try:
                await pubsub.subscribe(f"notify:{node_id}")
                async for message in pubsub.listen():
                    if message.get("type") == "message":
                        try:
                            live_seq = int(message["data"])
                            await stream_buffer.put(live_seq)
                        except Exception:
                            break  # Exit loop on error
            except asyncio.CancelledError:
                # Don't re-raise, just clean up
                pass
            except Exception as e:
                print(f"Live subscription error: {e}")
            finally:
                # More robust cleanup with timeouts
                try:
                    await asyncio.wait_for(
                        pubsub.unsubscribe(f"notify:{node_id}"), timeout=1.0
                    )
                except (asyncio.TimeoutError, Exception):
                    pass

                try:
                    await asyncio.wait_for(pubsub.aclose(), timeout=1.0)
                except (asyncio.TimeoutError, Exception):
                    pass

                try:
                    await asyncio.wait_for(ws_redis_client.aclose(), timeout=1.0)
                except (asyncio.TimeoutError, Exception):
                    pass

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
                live_seq = await stream_buffer.get()
                await stream_data(live_seq)
            else:
                await websocket.close(code=1000, reason="Producer ended stream")
        except WebSocketDisconnect:
            pass
        finally:
            # Properly cancel and wait for the live task to cleanup with timeout
            live_task.cancel()
            try:
                await asyncio.wait_for(live_task, timeout=2.0)
            except asyncio.CancelledError:
                pass  # Expected when cancelling
            except asyncio.TimeoutError:
                pass
            except Exception:
                pass

    @app.get("/stream/live")
    async def list_live_streams():
        nodes = await redis_client.keys("seq_num:*")
        return [node.decode("utf-8").split(":")[1] for node in nodes]

    return app


settings = Settings()
app = build_app(settings)

if __name__ == "__main__":
    uvicorn.run(app)
