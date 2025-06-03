from httpx import AsyncClient, Client
import asyncio
import websockets
import numpy as np
import json
import msgpack
import os
# from httpx_ws import aconnect_ws
# from httpx_ws.transport import ASGIWebSocketTransport

# async def stream_listener(path):
#         nonlocal ac
#         subprotocols = ["application/octet-stream"]

#         async with aconnect_ws(
#             f"http://localhost/stream/{path}?cursor=1", ac,
#             subprotocols=subprotocols,
#         ) as ws:
#             for i in range(3):
#                 message = await ws.receive_bytes()
#                 data = np.frombuffer(message, dtype=np.int64)
#                 print(f"client received data {path = }, {data=}")
#                 await asyncio.sleep(1)

#     ac = AsyncClient(
#         transport=ASGIWebSocketTransport(app=app), base_url="http://localhost"
#     )

# Get base URL from environment variable, default to localhost
REDIS_WS_API_URL = os.getenv("REDIS_WS_API_URL", "localhost:8000")
client = AsyncClient(base_url=f"http://{REDIS_WS_API_URL}")


async def get_live():
    result = await client.get("/stream/live")
    return result.json()

async def stream_node(node_id: str, envelope_format="json"):
    # Create WebSocket URL from base URL
    websocket_url = f"ws://{REDIS_WS_API_URL}/stream/single/{node_id}?envelope_format={envelope_format}&seq_num=1"

    async with websockets.connect(websocket_url) as websocket:
        print(f"Connected to {websocket_url}")

        try:
            while True:
                message = await websocket.recv()
                if isinstance(message, bytes) and envelope_format == 'msgpack':
                    message = msgpack.unpackb(message)
                    print(f"Received Msgpack: {message}")
                else:
                    print(f"Received JSON: {json.loads(message)}")
        except websockets.exceptions.ConnectionClosed as e:
            print(f"Connection closed {e}")


async def main():
    result = await get_live()
    print(result)
    await stream_node('481980', envelope_format="msgpack")

asyncio.run(main())
