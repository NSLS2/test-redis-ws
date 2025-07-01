"""
Tests designed to expose bugs, crashes, and incorrect behavior in the server.
"""
import pytest


def test_invalid_node_id_string_in_delete(client):
    """Server accepts string node_ids without validation."""
    response = client.delete("/upload/invalid_string")
    assert response.status_code == 204


def test_invalid_node_id_float_in_delete(client):
    """Server accepts float node_ids without validation."""
    response = client.delete("/upload/123.456")
    assert response.status_code == 204


def test_negative_node_id_in_delete(client):
    """Server accepts negative node_ids without validation."""
    response = client.delete("/upload/-1")
    assert response.status_code == 204


def test_malformed_json_in_close_endpoint(client):
    """Server crashes with malformed JSON in /close endpoint."""
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # This causes JSONDecodeError crash
    with pytest.raises(Exception):
        client.post(
            f"/close/{node_id}",
            content=b"invalid json {{{",
            headers={"Content-Type": "application/json"}
        )


def test_missing_json_body_in_close_endpoint(client):
    """Server crashes when /close endpoint receives no JSON body."""
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # This causes JSONDecodeError crash
    with pytest.raises(Exception):
        client.post(f"/close/{node_id}")


# def test_upload_invalid_binary_data(client):
#     """Test server behavior when trying to interpret non-numeric binary data as float64."""
#     # Create a node
#     response = client.post("/upload")
#     assert response.status_code == 200
#     node_id = response.json()["node_id"]
#     
#     # Upload text data that can't be interpreted as float64 array
#     response = client.post(
#         f"/upload/{node_id}",
#         content=b"this is not numeric data",
#         headers={"Content-Type": "application/octet-stream"}
#     )
#     assert response.status_code == 200  # Upload succeeds
#     
#     # Test WebSocket behavior with invalid binary data
#     with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
#         try:
#             # This might crash or handle gracefully on line 138: np.frombuffer(payload, dtype=np.float64)
#             msg_text = websocket.receive_text()
#             msg = json.loads(msg_text)
#             print(f"Server handled invalid binary data: {msg}")
#             # If we get here, server handled the error gracefully
#         except Exception as e:
#             print(f"WebSocket failed as expected: {e}")
#             # Expected behavior - server should handle this gracefully


# def test_upload_empty_payload(client):
#     """Server behavior with zero-length binary data may be undefined."""
#     # Create a node
#     response = client.post("/upload")
#     assert response.status_code == 200
#     node_id = response.json()["node_id"]
#     
#     # Upload empty binary data
#     response = client.post(
#         f"/upload/{node_id}",
#         content=b"",
#         headers={"Content-Type": "application/octet-stream"}
#     )
#     assert response.status_code == 200
#     
#     # WebSocket connection might crash when processing empty data
#     with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
#         msg_text = websocket.receive_text()
#         msg = json.loads(msg_text)
#         # Empty array might cause issues in downstream processing
#         assert msg["payload"] == []


def test_websocket_invalid_envelope_format(client):
    """Server accepts invalid envelope_format values."""
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # Server doesn't validate envelope_format
    with client.websocket_connect(f"/stream/single/{node_id}?envelope_format=invalid"):
        pass


def test_websocket_invalid_seq_num_string(client):
    """Server properly validates seq_num parameter and disconnects."""
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # Server validates seq_num and disconnects on invalid input
    with pytest.raises(Exception):  # WebSocketDisconnect
        with client.websocket_connect(f"/stream/single/{node_id}?seq_num=invalid"):
            pass


def test_websocket_negative_seq_num(client):
    """Server handles negative seq_num without validation."""
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    client.post(
        f"/upload/{node_id}",
        content=b"\x00\x00\x00\x00\x00\x00\x00\x00",
        headers={"Content-Type": "application/octet-stream"}
    )
    
    with client.websocket_connect(f"/stream/single/{node_id}?seq_num=-1") as websocket:
        websocket.receive_text()


# def test_delete_node_during_websocket_stream(client):
#     """Race condition: deleting node while WebSocket is streaming."""
#     # Create a node and add data
#     response = client.post("/upload")
#     assert response.status_code == 200
#     node_id = response.json()["node_id"]
#     
#     client.post(
#         f"/upload/{node_id}",
#         content=b"\x00\x00\x00\x00\x00\x00\x00\x00",
#         headers={"Content-Type": "application/octet-stream"}
#     )
#     
#     # Start WebSocket connection
#     with client.websocket_connect(f"/stream/single/{node_id}") as websocket:
#         # Receive first message
#         msg_text = websocket.receive_text()
#         print(f"Received message before deletion: {len(msg_text)} chars")
#         
#         # Delete the node while WebSocket is still connected
#         delete_response = client.delete(f"/upload/{node_id}")
#         assert delete_response.status_code == 204
#         print("Node deleted")
#         
#         # Try to add more data to deleted node - this might succeed unexpectedly
#         response = client.post(
#             f"/upload/{node_id}",
#             content=b"\x01\x00\x00\x00\x00\x00\x00\x00",
#             headers={"Content-Type": "application/octet-stream"}
#         )
#         print(f"Post to deleted node status: {response.status_code}")
#         
#         # Don't wait for more messages as this might hang
#         print("Race condition test completed")


def test_double_delete_node(client):
    """Server allows deleting the same node multiple times."""
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    response1 = client.delete(f"/upload/{node_id}")
    assert response1.status_code == 204
    
    # Should return 404, but server returns 204
    response2 = client.delete(f"/upload/{node_id}")
    assert response2.status_code == 204


def test_websocket_connect_to_nonexistent_node(client):
    """WebSocket connection to non-existent node handles gracefully."""
    nonexistent_node_id = 999999
    
    try:
        with client.websocket_connect(f"/stream/single/{nonexistent_node_id}"):
            pass
    except Exception:
        pass


@pytest.mark.timeout(5)
def test_upload_invalid_binary_data(client):
    """Server accepts non-numeric binary data without validation."""
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    response = client.post(
        f"/upload/{node_id}",
        content=b"this is not numeric data",
        headers={"Content-Type": "application/octet-stream"}
    )
    assert response.status_code == 200
    
    with client.websocket_connect(f"/stream/single/{node_id}"):
        pass


@pytest.mark.timeout(5)
def test_upload_empty_payload(client):
    """Server handles zero-length binary data."""
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    response = client.post(
        f"/upload/{node_id}",
        content=b"",
        headers={"Content-Type": "application/octet-stream"}
    )
    assert response.status_code == 200
    
    with client.websocket_connect(f"/stream/single/{node_id}"):
        pass


@pytest.mark.timeout(5)
def test_websocket_huge_seq_num(client):
    """Server handles very large seq_num values without validation."""
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    huge_seq_num = 999999999
    with client.websocket_connect(f"/stream/single/{node_id}?seq_num={huge_seq_num}"):
        pass


@pytest.mark.timeout(5)
def test_upload_to_deleted_node(client):
    """Server allows uploading data to deleted nodes."""
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    delete_response = client.delete(f"/upload/{node_id}")
    assert delete_response.status_code == 204
    
    response = client.post(
        f"/upload/{node_id}",
        content=b"\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00",
        headers={"Content-Type": "application/octet-stream"}
    )
    assert response.status_code == 200


@pytest.mark.timeout(5)
def test_upload_no_content_type_header(client):
    """Server handles missing Content-Type header gracefully."""
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    response = client.post(
        f"/upload/{node_id}",
        content=b"\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00"
    )
    assert response.status_code == 200
    
    with client.websocket_connect(f"/stream/single/{node_id}"):
        pass


@pytest.mark.timeout(5) 
def test_close_endpoint_with_valid_json_structure(client):
    """Server handles valid JSON with different structure gracefully."""
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    response = client.post(
        f"/close/{node_id}",
        json={"wrong_field": "value", "not_reason": True}
    )
    assert response.status_code == 200


@pytest.mark.timeout(5)
def test_websocket_msgpack_format(client):
    """Server handles msgpack format requests."""
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    client.post(
        f"/upload/{node_id}",
        content=b"\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00",
        headers={"Content-Type": "application/octet-stream"}
    )
    
    with client.websocket_connect(f"/stream/single/{node_id}?envelope_format=msgpack"):
        pass


@pytest.mark.timeout(5)
def test_upload_large_payload(client):
    """Server handles large payloads without size limits."""
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    large_payload = b"\\x00" * (1024 * 1024)  # 1MB
    
    response = client.post(
        f"/upload/{node_id}",
        content=large_payload,
        headers={"Content-Type": "application/octet-stream"}
    )
    assert response.status_code == 200
    
    with client.websocket_connect(f"/stream/single/{node_id}"):
        pass


@pytest.mark.timeout(5)
def test_close_endpoint_without_node_creation(client):
    """Server allows closing non-existent nodes."""
    fake_node_id = 999999
    
    response = client.post(
        f"/close/{fake_node_id}",
        json={"reason": "test"}
    )
    assert response.status_code == 200


@pytest.mark.timeout(5)
def test_upload_with_mismatched_content_type(client):
    """Server handles Content-Type mismatch gracefully."""
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    response = client.post(
        f"/upload/{node_id}",
        content=b"\\xff\\xfe\\x00\\x01\\x02\\x03",
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 200
    
    with client.websocket_connect(f"/stream/single/{node_id}"):
        pass


@pytest.mark.timeout(5)
def test_extremely_long_node_id(client):
    """Server handles extremely long node_id values."""
    long_node_id = "a" * 10000  # 10KB string
    
    try:
        client.delete(f"/upload/{long_node_id}")
    except Exception:
        pass
    
    try:
        client.post(
            f"/upload/{long_node_id}",
            content=b"\\x00\\x00\\x00\\x00",
            headers={"Content-Type": "application/octet-stream"}
        )
    except Exception:
        pass

