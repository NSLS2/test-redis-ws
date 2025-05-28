import numpy as np
import httpx
import time
import sys

client = httpx.Client(base_url="http://localhost:8000")


def main():
    for _ in range(3):
        #content = client.post("/upload").raise_for_status().json()
        #node_id = content["node_id"]
        node_id = 481980
        for i in range(10):
            time.sleep(0.5)
            binary_data = (np.ones(5) * i).tobytes()
            client.post(
                f"/upload/{node_id}",
                data=binary_data,
                headers={"Content-Type": "application/octet-stream"},
            ).raise_for_status()
        client.delete(f"/upload/{node_id}").raise_for_status()
    if '--close' in sys.argv:
        print("Closing stream")
        client.post(f"/close/{node_id}", json={"reason": "Experiment complete"})

main()
