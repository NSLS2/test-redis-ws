from locust import HttpUser, task, between, events
from locust_plugins.users.socketio import SocketIOUser
import numpy as np
import time
import json
import msgpack
import logging
from datetime import datetime
import random

class E2ELatencyUser(HttpUser, SocketIOUser):
    """User that measures write-to-read latency"""
    wait_time = between(0.5, 1)  # Give time for messages to arrive

    def on_start(self):
        # Use random node_id.
        self.node_id = random.randint(100000, 999999)
        self.writes = {}  # Track writes waiting for reads
        self.latencies = []
        self.seq_num = 0  # Sequential counter for write values
        self.messages_received = 0
        self.writes_expired = 0  # Track writes that timed out

        # Connect WebSocket for reading - don't request historical data
        ws_url = f"ws://{self.host.replace('http://', '').replace('https://', '')}/stream/single/{self.node_id}?envelope_format=msgpack"
        self.connect(ws_url)
        logging.info(f"Connected to WebSocket for node {self.node_id}")


    def on_message(self, message):
        """Handle incoming WebSocket messages and calculate latency"""
        try:
            received_time = time.time()

            if isinstance(message, bytes):
                data = msgpack.unpackb(message)
            else:
                data = json.loads(message)

            self.messages_received += 1

            # Extract the payload and decode our seq_num from it
            payload = data.get('payload', [])
            if payload and len(payload) > 0:
                # The seq_num we wrote is the value in the numpy array
                our_seq_num = int(payload[0])

                # Check if we're tracking this message
                if our_seq_num in self.writes:
                    write_time = self.writes[our_seq_num]
                    latency_ms = (received_time - write_time) * 1000

                    logging.info(f"E2E latency for our seq_num {our_seq_num} (server sequence {data.get('sequence')}): {latency_ms:.1f}ms")
                    self.latencies.append(latency_ms)

                    # Report to Locust
                    events.request.fire(
                        request_type="E2E",
                        name="write_to_websocket_delivery",
                        response_time=latency_ms,
                        response_length=0,
                        exception=None
                    )

                    # Clean up tracking
                    del self.writes[our_seq_num]

        except Exception as e:
            logging.error(f"Error processing message: {e}")

    @task
    def write_and_measure(self):
        """Write data and track when it arrives via WebSocket"""
        # Use incrementing counter for write value
        binary_data = (np.ones(5) * self.seq_num).tobytes()

        # Track this write BEFORE sending (to handle race condition)
        write_time = time.time()
        self.writes[self.seq_num] = write_time
        current_seq = self.seq_num
        self.seq_num += 1

        # Write data
        response = self.client.post(
            f"/upload/{self.node_id}",
            data=binary_data,
            headers={"Content-Type": "application/octet-stream"},
            name="write_for_e2e"
        )

        if response.status_code == 200:
            logging.info(f"Wrote message with our seq_num {current_seq} to node {self.node_id}")
        else:
            # Remove from tracking if write failed
            if current_seq in self.writes:
                del self.writes[current_seq]

    def on_stop(self):
        # Log final statistics
        logging.info(f"User {self.node_id} stats: writes={self.seq_num}, messages_received={self.messages_received}, "
                    f"matched={len(self.latencies)}, expired={self.writes_expired}, in_flight={len(self.writes)}")

        # Disconnect WebSocket
        if hasattr(self, 'ws') and self.ws:
            self.ws.close()
