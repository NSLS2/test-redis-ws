from httpx import AsyncClient, Client
import asyncio

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

client = AsyncClient(base_url="http://localhost:8000")


async def get_live():
    result = await client.get("/stream/live")
    return result.json()


result = asyncio.run(get_live())
print(result)
