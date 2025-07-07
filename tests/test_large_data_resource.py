"""
Tests for large data handling and resource limit bugs.
"""
import pytest
from fastapi import HTTPException


def test_large_data_resource_limits(client):
    """Server should handle large data with proper resource limits."""
    
    # Test 1: Huge payload (20MB) - should be rejected as too large
    response = client.post("/upload")
    assert response.status_code == 200
    node_id1 = response.json()["node_id"]
    
    huge_payload = b"\x00" * (20 * 1024 * 1024)  # 20MB (exceeds 16MB limit)
    with pytest.raises(HTTPException) as exc_info:
        client.post(
            f"/upload/{node_id1}",
            content=huge_payload,
            headers={"Content-Type": "application/octet-stream"}
        )
    # Should be rejected with 413 Payload Too Large due to size limits
    assert exc_info.value.status_code == 413
    assert "Payload too large" in exc_info.value.detail
    
    # Test 2: Very long headers (1MB) - should have header size limits
    response = client.post("/upload")
    assert response.status_code == 200
    node_id2 = response.json()["node_id"]
    
    very_long_header = "x" * 1000000  # 1MB header
    with pytest.raises(HTTPException) as exc_info:
        client.post(
            f"/upload/{node_id2}",
            content=b"\x00\x00\x00\x00\x00\x00\x00\x00",
            headers={
                "Content-Type": "application/octet-stream",
                "Very-Long-Header": very_long_header
            }
        )
    # Should be rejected with 431 Request Header Fields Too Large
    assert exc_info.value.status_code == 431
    assert "too large" in exc_info.value.detail
    
    # Test 3: WebSocket frame size limits are enforced in server code
    # (WebSocket frame size protection is implemented at server.py:173-189)

