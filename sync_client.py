from websockets.sync.client import connect
import json
import msgpack
import os

class NodePlaceholder:
    def __init__(self, node_id, envelope_format="json", base_url="localhost:8000"):
        self.node_id = node_id
        self.envelope_format = envelope_format
        self.base_url = base_url
    
    def stream(self, seq_num=None):
        websocket_url = f"ws://{self.base_url}/stream/single/{self.node_id}?envelope_format={self.envelope_format}"
        if seq_num is not None:
            websocket_url += f"&seq_num={seq_num}"
        
        with connect(websocket_url) as websocket:
            for message in websocket:
                if isinstance(message, bytes) and self.envelope_format == "msgpack":
                    yield msgpack.unpackb(message)
                else:
                    yield json.loads(message)


def main():
    REDIS_WS_API_URL = os.getenv("REDIS_WS_API_URL", "localhost:8000")
    
    node = NodePlaceholder(node_id="481980", envelope_format="msgpack", base_url=REDIS_WS_API_URL)
    
    for message in node.stream():
        print(f"Received: {message}")


if __name__ == "__main__":
    main()
