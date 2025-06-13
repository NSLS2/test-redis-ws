import os
from locust import HttpUser, task, between, events
from locust_plugins.users.socketio import SocketIOUser
import numpy as np
import time
import json
import msgpack
import logging
import httpx


class WriterUser(HttpUser):
    wait_time = between(0.1, 0.2)  # Wait 0.1-0.2 seconds between writes
    weight = int(os.getenv("WRITER_WEIGHT", 1))

    def on_start(self):
        """Initialize user state"""
        # Use a fixed node_id so StreamingUser can connect to it
        self.node_id = 481980
        self.message_count = 0

    @task(10)  # Run 10x as often as cleanup
    def write_data(self):

        # Create data with incrementing value
        binary_data = (np.ones(5) * time.time()).tobytes()

        # Post data and check response
        response = self.client.post(
            f"/upload/{self.node_id}",
            data=binary_data,
            headers={"Content-Type": "application/octet-stream"},
        )

        # Log status like writing_client
        if response.status_code == httpx.codes.OK:
            logging.info(f"Wrote message {self.message_count} to node {self.node_id}")
            self.message_count += 1
        else:
            logging.error(
                f"Failed to write message {self.message_count}: {response.status_code}"
            )

    @task
    def cleanup(self):
        """Periodically delete the node like the real client"""
        if self.message_count > 20:
            self.client.delete(f"/upload/{self.node_id}")
            self.message_count = 0
            logging.info(f"Cleaned up node {self.node_id}")


class StreamingUser(SocketIOUser):
    """User that streams data from test-redis-ws"""

    wait_time = between(0.1, 0.2)
    weight = int(os.getenv("STREAMING_WEIGHT", 1))

    def on_start(self):
        """Connect to the streaming endpoint"""
        # Use the same node_id as WriterUser
        self.node_id = 481980
        self.envelope_format = "msgpack"  # or "json"

        # Connect to WebSocket endpoint
        ws_url = f"ws://{self.host.replace('http://', '').replace('https://', '')}/stream/single/{self.node_id}?envelope_format={self.envelope_format}"
        self.connect(ws_url)

    def on_message(self, message):
        """Process websocket messages and measure latency"""
        try:
            received_time = time.time()

            if isinstance(message, bytes):
                data = msgpack.unpackb(message)
            else:
                data = json.loads(message)

            # Pull out timestamp from the payload
            payload = data.get("payload", [])
            if payload and len(payload) > 0:
                write_time = float(payload[0])
                latency_ms = (received_time - write_time) * 1000

                logging.info(
                    f"WS latency (server sequence {data.get('sequence')}): {latency_ms:.1f}ms"
                )

                events.request.fire(
                    request_type="WS",
                    name="write_to_websocket_delivery",
                    response_time=latency_ms,
                    response_length=0,
                    exception=None,
                )

        except Exception as e:
            logging.error(f"Error processing message: {e}")

    @task
    def keep_alive(self):
        """Dummy task to keep the user active while listening for messages"""
        pass
