import numpy as np
import httpx
import time
import sys
import os
from datetime import datetime

# Get base URL from environment variable, default to localhost
REDIS_WS_API_URL = os.getenv("REDIS_WS_API_URL", "localhost:8000")
client = httpx.Client(base_url=f"http://{REDIS_WS_API_URL}")

# Get write delay from environment variable, default to 0.5 seconds
WRITE_DELAY = float(os.getenv("WRITE_DELAY", "0.5"))

# Get number of writes from environment variable, default to 10
NUM_WRITES = int(os.getenv("NUM_WRITES", "10"))


def main():
    for run in range(3):
        #content = client.post("/upload").raise_for_status().json()
        #node_id = content["node_id"]
        node_id = 481980
        print(f"Writing {run=}")
        for i in range(NUM_WRITES):
            time.sleep(WRITE_DELAY)
            binary_data = (np.ones(5) * i).tobytes()
            client.post(
                f"/upload/{node_id}",
                data=binary_data,
                headers={"Content-Type": "application/octet-stream"},
            ).raise_for_status()
            print(f"Wrote message {i} to node {node_id}")
        print(f"Completed {NUM_WRITES} writes")
        client.delete(f"/upload/{node_id}").raise_for_status()
        print(f"Deleted node {node_id}")
    if '--close' in sys.argv:
        print("Closing stream")
        client.post(f"/close/{node_id}", json={"reason": "Experiment complete"})
    print("\nWriterfinished successfully")

main()
