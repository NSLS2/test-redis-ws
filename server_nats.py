import json
import numpy as np
import uvicorn
from pydantic_settings import BaseSettings
from fastapi import FastAPI, WebSocket, Request, WebSocketDisconnect
from pydantic import BaseModel
from datetime import datetime
import msgpack
import asyncio
from typing import Optional
import socket

from nats.aio.client import Client as NATS
from nats.js.kv import KeyValue
from nats.js.errors import KeyNotFoundError

class Settings(BaseSettings):
    nats_url: str = "nats://localhost:4222"
    kv_bucket: str = "datasets"
    ttl: int = 60 * 60  # 1 hour

async def get_nats_kv(settings: Settings):
    nc = NATS()
    await nc.connect(servers=[settings.nats_url])
    js = nc.jetstream()
    try:
        kv = await js.key_value(settings.kv_bucket)
    except Exception:
        # Create the bucket if it doesn't exist
        await js.create_key_value(bucket=settings.kv_bucket, history=1, ttl=settings.ttl)
        kv = await js.key_value(settings.kv_bucket)
    return nc, kv

def build_app(settings: Settings):
    app = FastAPI()
    nats_ready = asyncio.Event()
    nats_state = {}

    @app.on_event("startup")
    async def startup_event():
        nc, kv = await get_nats_kv(settings)
        nats_state["nc"] = nc
        nats_state["kv"] = kv
        nats_ready.set()

    @app.on_event("shutdown")
    async def shutdown_event():
        nc = nats_state.get("nc")
        if nc:
            await nc.close()

    @app.middleware("http")
    async def add_server_header(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Server-Host"] = socket.gethostname()
        return response

    @app.post("/upload")
    async def create():
        await nats_ready.wait()
        kv: KeyValue = nats_state["kv"]
        # Generate a random node_id.
        # (In Tiled, PostgreSQL will give us a unique ID.)
        node_id = np.random.randint(1_000_000)
        await kv.create(f"seq_num:{node_id}", b"0")
        return {"node_id": node_id}

    @app.delete("/upload/{node_id}", status_code=204)
    async def close(node_id):
        await nats_ready.wait()
        kv: KeyValue = nats_state["kv"]
        await kv.delete(f"seq_num:{node_id}")
        return None

    @app.post("/upload/{node_id}")
    async def append(node_id, request: Request):
        await nats_ready.wait()
        kv: KeyValue = nats_state["kv"]
        binary_data = await request.body()
        headers = request.headers
        metadata = {
            "timestamp": datetime.now().isoformat(),
        }
        metadata.setdefault("Content-Type", headers.get("Content-Type"))

        # Increment the counter for this node.
        seq_key = f"seq_num:{node_id}"
        try:
            seq_num = int((await kv.get(seq_key)).value.decode())
        except KeyNotFoundError:
            seq_num = 0  # If the key doesn't exist, start from 0
        seq_num += 1
        await kv.put(seq_key, str(seq_num).encode())

        # Store data in KV
        data_key = f"data:{node_id}:{seq_num}"
        value = {
            "metadata": metadata,
            "payload": binary_data.hex(),  # Store as hex string
        }
        await kv.put(data_key, json.dumps(value).encode())

        # Publish notification
        nc = nats_state["nc"]
        await nc.publish(f"notify.{node_id}", str(seq_num).encode())

    @app.post("/close/{node_id}")
    async def close_connection(node_id: str, request: Request):
        await nats_ready.wait()
        kv: KeyValue = nats_state["kv"]
        nc = nats_state["nc"]

        body = await request.json()
        headers = request.headers
        reason = body.get("reason", None)
        metadata = {
            "timestamp": datetime.now().isoformat(),
            "reason": reason
        }
        metadata.setdefault("Content-Type", headers.get("Content-Type"))

        seq_key = f"seq_num:{node_id}"
        seq_num = int((await kv.get(seq_key)).value.decode())
        seq_num += 1
        await kv.put(seq_key, str(seq_num).encode())

        data_key = f"data:{node_id}:{seq_num}"
        value = {
            "metadata": metadata,
            "payload": None,
        }
        await kv.put(data_key, json.dumps(value).encode())
        await nc.publish(f"notify.{node_id}", str(seq_num).encode())

        return {
            "status": f"Connection for node {node_id} is now closed.",
            "reason": reason
        }

    @app.websocket("/stream/single/{node_id}")
    async def websocket_endpoint(websocket: WebSocket,
                                 node_id: str,
                                 envelope_format: str = "json",
                                 seq_num: Optional[int] = None):
        await nats_ready.wait()
        kv: KeyValue = nats_state["kv"]
        nc = nats_state["nc"]

        await websocket.accept(headers=[
            (b"x-server-host", socket.gethostname().encode())
        ])
        end_stream = asyncio.Event()

        async def stream_data(seq_num):
            key = f"data:{node_id}:{seq_num}"
            try:
                entry = await kv.get(key)
                value = json.loads(entry.value.decode())
                metadata = value["metadata"]
                payload = value["payload"]
                if payload is not None:
                    try:
                        payload = np.frombuffer(bytes.fromhex(payload), dtype=np.float64).tolist()
                    except Exception:
                        payload = json.loads(payload)
                data = {
                    "sequence": seq_num,
                    "metadata": metadata,
                    "payload": payload,
                    "server_host": socket.gethostname()
                }
                if envelope_format == "msgpack":
                    await websocket.send_bytes(msgpack.packb(data))
                else:
                    await websocket.send_text(json.dumps(data))
                if payload is None and metadata is not None:
                    end_stream.set()
            except Exception:
                return

        stream_buffer = asyncio.Queue()

        async def buffer_live_events():
            sub = await nc.subscribe(f"notify.{node_id}")
            try:
                async for msg in sub.messages:
                    try:
                        live_seq = int(msg.data.decode())
                        await stream_buffer.put(live_seq)
                    except Exception as e:
                        print(f"Error parsing live message: {e}")
            except Exception as e:
                print(f"Live subscription error: {e}")
            finally:
                await sub.unsubscribe()

        live_task = asyncio.create_task(buffer_live_events())

        if seq_num is not None:
            current_seq = int((await kv.get(f"seq_num:{node_id}")).value.decode())
            for s in range(seq_num, current_seq + 1):
                await stream_data(s)
        try:
            while not end_stream.is_set():
                live_seq = await stream_buffer.get()
                await stream_data(live_seq)
            else:
                await websocket.close(code=1000, reason="Producer ended stream")
        except WebSocketDisconnect:
            print(f"Client disconnected from node {node_id}")
        finally:
            live_task.cancel()

    @app.get("/stream/live")
    async def list_live_streams():
        await nats_ready.wait()
        kv: KeyValue = nats_state["kv"]
        keys = await kv.keys()
        nodes = [key.split(":")[1] for key in keys if key.startswith("seq_num:")]
        return nodes

    return app

settings = Settings()
app = build_app(settings)

if __name__ == "__main__":
    uvicorn.run(app)