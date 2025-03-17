import redis
import json
import numpy as np
import uvicorn
from pydantic_settings import BaseSettings
from fastapi import FastAPI, WebSocket, Request
from pydantic import BaseModel
from datetime import datetime


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"
    ttl: int = 60 * 60  # 1 hour


# class Data(BaseModel):
#     metadata: dict
#     payload: bytes


def build_app(settings: Settings):
    redis_client = redis.from_url(settings.redis_url)

    node_id = 42

    app = FastAPI()

    @app.post("/upload")
    def create():
        "Declare a new dataset."
        # Generate a rnadom node_id.
        # (In Tiled, PostgreSQL will give us a unique ID.)
        node_id = np.random.randint(1_000_000)
        # Allocate a counter for this node_id.
        redis_client.setnx(f"seq_num:{node_id}", 0)
        return {"node_id": node_id}

    @app.delete("/upload/{node_id}")
    def close(node_id):
        "Declare that a dataset is done streaming."
        redis_client.delete(f"seq_num:{node_id}")
        # TODO: Shorten TTL on all extant data for this node.

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
        seq_num = redis_client.incr(f"seq_num:{node_id}")

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
        pipeline.execute()
        print(
            np.frombuffer(
                redis_client.hget(f"data:{node_id}:{seq_num}", "payload"),
                dtype=np.float64,
            )
        )

    # TODO: Implement two-way communication with subscribe, unsubscribe, flow control.
    #   @app.websocket("/stream/many")

    @app.websocket("/stream/one/{node_id}")  # one-way communcation
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Message text was: {data}")

    @app.get("/stream/live")
    async def list_live_streams():
        nodes = redis_client.keys("seq_num:*")
        return [node.decode("utf-8").split(":")[1] for node in nodes]

    # @app.websocket("/stream/{path:path}/{uid}")
    # async def websocket_endpoint(
    #     path: str, uid: str, websocket: WebSocket, cursor: int | None = None
    # ):
    #     """
    #     WebSocket endpoint to stream dataset records to the client.

    #     Parameters
    #     ----------
    #     uid : str
    #         unique indentifier for the dataset.
    #     path : str
    #         catalog path.
    #     websocket : WebSocket
    #         WebSocket connection instance.
    #     cursor : int, optional
    #         Starting position in the dataset (default is 0).
    #     """

    #     # How do you know when a dataset is completed?
    #     subprotocols = ["v1"]
    #     mimetypes = ["*/*", "application/json"]
    #     mimetype, subprotocol = await websocket_accept(
    #         websocket, mimetypes, subprotocols
    #     )

    #     while True:
    #         async with app.pool.acquire() as connection:
    #             result = await connection.fetchrow(
    #                 f"SELECT * FROM datasets WHERE uid='{uid}' AND path='{path}' LIMIT 1;"
    #             )
    #             if result is not None:
    #                 path, uid, data, length = result
    #                 if cursor is None:
    #                     cursor = length
    #                 print(f"server {path = }, {data = }")
    #                 while cursor < length:
    #                     if mimetype == "application/json":
    #                         await websocket.send_json({"record": data[cursor]})
    #                     elif mimetype == "application/octet-stream":
    #                         await websocket.send_bytes(np.array(data[cursor]).tobytes())
    #                     elif mimetype == "image/tiff":
    #                         with open(f"image.tiff", "rb") as tiff:
    #                             await websocket.send_bytes(tiff.read())
    #                     else:
    #                         raise WebSocketException(
    #                             f"Invalid subprotocol: {subprotocols}"
    #                         )
    #                     cursor += 1
    #             await asyncio.sleep(1)

    return app


settings = Settings()
app = build_app(settings)

if __name__ == "__main__":
    uvicorn.run(app)
