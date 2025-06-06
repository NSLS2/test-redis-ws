from locust import HttpUser, task, between
import numpy as np
import time

class WriterUser(HttpUser):
    wait_time = between(0.1, 0.2)  # Wait 0.5-2 seconds between writes

    def on_start(self):
        """Initialize user state"""
        self.node_id = 481980
        self.message_count = 0

    @task(2)  # Run twice as often as cleanup
    def write_data(self):
        # Sleep before writing (like WRITE_DELAY)
        time.sleep(0.1)

        # Create data with incrementing value
        binary_data = (np.ones(5) * self.message_count).tobytes()

        # Post data and check response
        response = self.client.post(
            f"/upload/{self.node_id}",
            data=binary_data,
            headers={"Content-Type": "application/octet-stream"}
        )

        # Print status like writing_client
        if response.status_code == 200:
            print(f"Wrote message {self.message_count} to node {self.node_id}")
            self.message_count += 1
        else:
            print(f"Failed to write message {self.message_count}: {response.status_code}")

    @task
    def cleanup(self):
        """Periodically delete the node like the real client"""
        if self.message_count > 20:
            self.client.delete(f"/upload/{self.node_id}")
            self.message_count = 0
            print(f"Cleaned up node {self.node_id}")
