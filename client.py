import numpy as np
import httpx
import msgpack

client = httpx.Client(base_url="http://localhost:8000")


def main():
    for _ in range(10):
        metadata = {
            "timestamp": "2021-01-01T00:00:00",
            "source": "sensor_1",
            "data_type": "temperature",
        }
        content = client.post("/upload").raise_for_status().json()
        node_id = content["node_id"]
        for i in range(10):
            binary_data = (np.ones(5) * i).tobytes()
            data = msgpack.packb({"metadata": metadata, "payload": binary_data})
            client.post(f"/upload/{node_id}", data=data).raise_for_status()
        client.delete(f"/upload/{node_id}").raise_for_status()
        # print(
        #     np.frombuffer(
        #         redis_client.hget(f"data:{node_id}:{seq_num}", "payload"),
        #         dtype=np.float64,
        #     )
        # )


main()
