"""
Tests for JSON parsing error handling bugs in server endpoints.
"""


def test_json_parsing_errors_in_close_endpoint(client):
    """Server should handle JSON parsing errors in /close endpoint gracefully."""
    # FIXED: Added proper error handling in server.py:92-95 to prevent JSONDecodeError crashes
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]

    # Test 1: Malformed JSON content should not crash
    response = client.post(
        f"/close/{node_id}",
        content=b"invalid json {{{",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert "invalid JSON syntax" in response.json()["detail"]

    # Test 2: Missing JSON body should not crash
    response = client.post(f"/close/{node_id}")
    assert response.status_code == 400
    assert "valid JSON" in response.json()["detail"]
