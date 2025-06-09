import os
import random
from locust import HttpUser, task, between
from locust_plugins.users.socketio import SocketIOUser
import numpy as np
import time
import json
import msgpack
import logging


class WriterUser(HttpUser):
    wait_time = between(0.1, 0.2)  # Wait 0.1-0.2 seconds between writes
    weight = int(os.getenv('WRITER_WEIGHT', 1))

    def on_start(self):
        """Initialize user state"""
        # Use a fixed node_id so StreamingUser can connect to it
        self.node_id = 481980
        self.message_count = 0

    @task(10)  # Run 10x as often as cleanup
    def write_data(self):

        # Create data with incrementing value
        binary_data = (np.ones(5) * self.message_count).tobytes()

        # Post data and check response
        response = self.client.post(
            f"/upload/{self.node_id}",
            data=binary_data,
            headers={"Content-Type": "application/octet-stream"}
        )

        # Log status like writing_client
        if response.status_code == 200:
            logging.info(f"Wrote message {self.message_count} to node {self.node_id}")
            self.message_count += 1
        else:
            logging.error(f"Failed to write message {self.message_count}: {response.status_code}")

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
    weight = int(os.getenv('STREAMING_WEIGHT', 1))

    def on_start(self):
        """Connect to the streaming endpoint"""
        # Use the same node_id as WriterUser
        self.node_id = 481980
        self.message_count = 0
        self.messages = []
        self.envelope_format = "msgpack"  # or "json"

        # Connect to WebSocket endpoint (no seq_num = only new messages)
        ws_url = f"ws://{self.host.replace('http://', '').replace('https://', '')}/stream/single/{self.node_id}?envelope_format={self.envelope_format}"
        self.connect(ws_url)

    def on_message(self, message):
        """Handle incoming messages"""
        self.message_count += 1

        # Handle different message formats
        if isinstance(message, bytes) and self.envelope_format == 'msgpack':
            parsed_message = msgpack.unpackb(message)
            logging.info(f"Received Msgpack: {parsed_message}")
            self.messages.append(parsed_message)
        else:
            parsed_message = json.loads(message)
            logging.info(f"Received JSON: {parsed_message}")
            self.messages.append(parsed_message)

    @task
    def wait_for_messages(self):
        """Wait for streaming messages"""
        # Clear previous messages
        self.messages = []

        # Wait for messages to arrive
        start_time = time.time()
        while len(self.messages) < 5 and time.time() - start_time < 10:
            time.sleep(0.1)

        logging.info(f"Received {len(self.messages)} messages in this task")

        # Small delay between tasks
        self.sleep_with_heartbeat(1)
