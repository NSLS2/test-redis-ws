"""
Tests for the close endpoint.
"""

def test_close_connection_success(client):
    """Test successful close of an existing connection."""
    # First create a node
    response = client.post("/upload")
    assert response.status_code == 200
    node_id = response.json()["node_id"]
    
    # Upload some data to ensure the node exists
    response = client.post(
        f"/upload/{node_id}",
        content=b"test data",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 200
    
    # Now close the connection
    response = client.delete(f"/close/{node_id}")
    assert response.status_code == 200
    assert response.json()["status"] == f"Connection for node {node_id} is now closed."

    # Now close the connection again.
    response = client.delete(f"/close/{node_id}")
    assert response.status_code == 404


def test_close_connection_not_found(client):
    """Test close endpoint returns 404 for non-existent node."""
    non_existent_node_id = "definitely_non_existent_node_99999999"
    
    response = client.delete(f"/close/{non_existent_node_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Node not found"
