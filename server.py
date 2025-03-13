import redis
import json
import numpy as np

redis_client = redis.from_url("redis://localhost:6379/0")

node_id = 42
redis_client.setnx(f"seq_num:{node_id}", 0)

for _ in range(10):
    seq_num = redis_client.incr(f"seq_num:{node_id}")
    metadata = {
        "timestamp": "2021-01-01T00:00:00",
        "source": "sensor_1",
        "data_type": "temperature",
    }
    binary_data = (np.ones(5) * seq_num).tobytes()

    redis_client.hset(
        f"data:{node_id}:{seq_num}",
        mapping={
            "metadata": json.dumps(metadata).encode("utf-8"),
            "payload": binary_data,  # Raw binary bytes
        },
    )

    print(
        np.frombuffer(
            redis_client.hget(f"data:{node_id}:{seq_num}", "payload"), dtype=np.float64
        )
    )
