from locust import task, between
from locust_plugins.users.socketio import SocketIOUser
import time
import json
import msgpack
import logging

class StreamingUser(SocketIOUser):
    """User that streams data from test-redis-ws"""

    wait_time = between(1, 2)

    def on_start(self):
        """Connect to the streaming endpoint"""
        self.node_id = "481980"
        self.message_count = 0
        self.messages = []
        self.envelope_format = "msgpack"  # or "json"

        # Connect to WebSocket endpoint
        ws_url = f"ws://{self.host.replace('http://', '').replace('https://', '')}/stream/single/{self.node_id}?envelope_format={self.envelope_format}&seq_num=1"
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
