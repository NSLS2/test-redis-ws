"""
Tests for large data handling and resource limit bugs.
"""


def test_large_data_resource_limits(client):
    """Server should handle large data with proper resource limits."""

    # Test: Huge payload (20MB) - should be rejected as too large
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]

    huge_payload = b"\x00" * (20 * 1024 * 1024)  # 20MB (exceeds 16MB limit)
    response = client.post(
        f"/upload/{node_id}",
        content=huge_payload,
        headers={"Content-Type": "application/octet-stream"},
    )
    # Should be rejected with 413 Payload Too Large due to size limits
    assert response.status_code == 413
    assert "Payload too large" in response.json()["detail"]
