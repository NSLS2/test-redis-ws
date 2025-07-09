import os
import sys
from locust import HttpUser, task, between, events
import numpy as np
import time
import logging
import httpx

# Add parent directory to path to import sync_client
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sync_client import NodePlaceholder


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


class StreamingUser(HttpUser):
    """User that streams data from test-redis-ws using sync_client"""

    wait_time = between(0.1, 0.2)
    weight = int(os.getenv("STREAMING_WEIGHT", 1))

    def on_start(self):
        """Connect to the streaming endpoint using sync_client"""
        # Use the same node_id as WriterUser
        self.node_id = 481980
        self.envelope_format = "msgpack"  # or "json"
        
        # Extract host from client base_url
        base_url = self.client.base_url.replace("http://", "").replace("https://", "")
        self.node = NodePlaceholder(str(self.node_id), envelope_format=self.envelope_format, base_url=base_url)

    def process_message(self, message):
        """Process websocket messages and measure latency"""
        try:
            received_time = time.time()

            # Pull out timestamp from the payload
            payload = message.get("payload", [])
            if payload and len(payload) > 0:
                write_time = float(payload[0])
                latency_ms = (received_time - write_time) * 1000

                logging.info(
                    f"WS latency (server sequence {message.get('sequence')}): {latency_ms:.1f}ms"
                )

                events.request.fire(
                    request_type="WS",
                    name="write_to_websocket_delivery",
                    response_time=latency_ms,
                    response_length=len(str(message)),
                    exception=None,
                    context={}
                )

        except Exception as e:
            logging.error(f"Error processing message: {e}")

    @task
    def stream_messages(self):
        """Stream messages using sync_client"""
        try:
            for message in self.node.stream():
                self.process_message(message)
                break  # Process one message per task execution
                
        except Exception as e:
            logging.error(f"Error in streaming: {e}")
            events.request.fire(
                request_type="WS",
                name="stream_connection",
                response_time=0,
                response_length=0,
                exception=e,
                context={}
            )
