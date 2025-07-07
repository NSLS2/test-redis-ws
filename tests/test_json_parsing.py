"""
Tests for JSON parsing error handling bugs in server endpoints.
"""
import pytest


def test_json_parsing_errors_in_close_endpoint(client):
    """Server should handle JSON parsing errors in /close endpoint gracefully."""
    # TODO: Fix JSONDecodeError crash in server.py:91 - add proper error handling
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # Test 1: Malformed JSON content should not crash
    response = client.post(
        f"/close/{node_id}",
        content=b"invalid json {{{",
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400  # Should return bad request, not crash
    
    # Test 2: Missing JSON body should not crash  
    response = client.post(f"/close/{node_id}")
    assert response.status_code == 400  # Should return bad request, not crash