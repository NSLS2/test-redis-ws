import redis
import json
import numpy as np
import uvicorn
import msgpack
from pydantic_settings import BaseSettings
from fastapi import FastAPI, WebSocket, Request
from pydantic import BaseModel


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
        raw_body = await request.body()
        data = msgpack.unpackb(raw_body)
        metadata = data["metadata"]
        binary_data = data["payload"]

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

    # TODO: Implement two-way communication with subscribe, unsubscribe, flow control.
    #   @app.websocket("/stream/many")

    @app.websocket("/stream/one/{node_id}")  # one-way communcation
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Message text was: {data}")

    return app


settings = Settings()
app = build_app(settings)

if __name__ == "__main__":
    uvicorn.run(app)
