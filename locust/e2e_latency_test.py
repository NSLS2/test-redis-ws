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
    """Measures true end-to-end latency from write to websocket delivery"""
    wait_time = between(0.5, 1)

    def on_start(self):
        # Random node_id for each user
        self.node_id = random.randint(100000, 999999)
        self.writes = {}
        self.latencies = []
        self.seq_num = 0
        self.messages_received = 0
        self.writes_expired = 0

        # Start websocket connection
        ws_url = f"ws://{self.host.replace('http://', '').replace('https://', '')}/stream/single/{self.node_id}?envelope_format=msgpack"
        self.connect(ws_url)
        logging.info(f"Connected to WebSocket for node {self.node_id}")


    def on_message(self, message):
        """Process websocket messages and measure latency"""
        try:
            received_time = time.time()

            if isinstance(message, bytes):
                data = msgpack.unpackb(message)
            else:
                data = json.loads(message)

            self.messages_received += 1

            # Pull out seq_num from the payload
            payload = data.get('payload', [])
            if payload and len(payload) > 0:
                our_seq_num = int(payload[0])

                # Match it with the write
                if our_seq_num in self.writes:
                    write_time = self.writes[our_seq_num]
                    latency_ms = (received_time - write_time) * 1000

                    logging.info(f"E2E latency for our seq_num {our_seq_num} (server sequence {data.get('sequence')}): {latency_ms:.1f}ms")
                    self.latencies.append(latency_ms)

                    events.request.fire(
                        request_type="E2E",
                        name="write_to_websocket_delivery",
                        response_time=latency_ms,
                        response_length=0,
                        exception=None
                    )

                    del self.writes[our_seq_num]

        except Exception as e:
            logging.error(f"Error processing message: {e}")

    @task
    def write_and_measure(self):
        """Write data and wait for it to come back via websocket"""
        # Encode seq_num in the data itself
        binary_data = (np.ones(5) * self.seq_num).tobytes()

        # Start timing before the write
        write_time = time.time()
        self.writes[self.seq_num] = write_time
        current_seq = self.seq_num
        self.seq_num += 1

        response = self.client.post(
            f"/upload/{self.node_id}",
            data=binary_data,
            headers={"Content-Type": "application/octet-stream"},
            name="write_for_e2e"
        )

        if response.status_code == 200:
            logging.info(f"Wrote message with our seq_num {current_seq} to node {self.node_id}")
        else:
            # Don't track failed writes
            if current_seq in self.writes:
                del self.writes[current_seq]

    def on_stop(self):
        # Summary stats
        logging.info(f"User {self.node_id} stats: writes={self.seq_num}, messages_received={self.messages_received}, "
                    f"matched={len(self.latencies)}, expired={self.writes_expired}, in_flight={len(self.writes)}")

        # Clean up websocket
        if hasattr(self, 'ws') and self.ws:
            self.ws.close()
