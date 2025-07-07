"""
Tests for WebSocket data processing edge cases and conversion errors.
"""
import json
import struct
import pytest


@pytest.mark.timeout(5)
def test_websocket_data_processing_edge_cases(client):
    """Server should handle various data processing edge cases gracefully."""
    # TODO: Fix data conversion errors in server.py:138-140 - np.frombuffer and json.loads fallback
    
    # Test 1: Invalid binary data (text that can't be interpreted as float64)
    response = client.post("/upload")
    assert response.status_code == 200
    node_id1 = response.json()["node_id"]
    
    response = client.post(
        f"/upload/{node_id1}",
        content=b"this is not numeric data",
        headers={"Content-Type": "application/octet-stream"}
    )
    assert response.status_code == 200
    
    with client.websocket_connect(f"/stream/single/{node_id1}") as websocket:
        msg_text = websocket.receive_text()
        msg = json.loads(msg_text)
        assert "payload" in msg  # Should handle gracefully via json.loads fallback
    
    # Test 2: Empty payload data
    response = client.post("/upload")
    assert response.status_code == 200
    node_id2 = response.json()["node_id"]
    
    response = client.post(
        f"/upload/{node_id2}",
        content=b"",
        headers={"Content-Type": "application/octet-stream"}
    )
    assert response.status_code == 200
    
    with client.websocket_connect(f"/stream/single/{node_id2}") as websocket:
        msg_text = websocket.receive_text()
        msg = json.loads(msg_text)
        assert msg["payload"] == []  # Should handle empty data gracefully
    
    # Test 3: Extreme float64 values (infinity, NaN)
    response = client.post("/upload")
    assert response.status_code == 200
    node_id3 = response.json()["node_id"]
    
    extreme_values = [float('inf'), float('-inf'), 1.7976931348623157e+308, -1.7976931348623157e+308]
    extreme_binary = b''.join(struct.pack('d', val) for val in extreme_values)
    
    response = client.post(
        f"/upload/{node_id3}",
        content=extreme_binary,
        headers={"Content-Type": "application/octet-stream"}
    )
    assert response.status_code == 200
    
    with client.websocket_connect(f"/stream/single/{node_id3}") as websocket:
        msg_text = websocket.receive_text()  # Should handle inf/NaN in JSON serialization
        assert len(msg_text) > 0
    
    # Test 4: Binary data that fails both np.frombuffer AND json.loads
    response = client.post("/upload")
    assert response.status_code == 200
    node_id4 = response.json()["node_id"]
    
    response = client.post(
        f"/upload/{node_id4}",
        content=b"\\xff\\xfe\\x00random\\x01invalid\\x02json",
        headers={"Content-Type": "application/octet-stream"}
    )
    assert response.status_code == 200
    
    with client.websocket_connect(f"/stream/single/{node_id4}") as websocket:
        msg_text = websocket.receive_text()  # Should handle double conversion failure
        assert len(msg_text) > 0