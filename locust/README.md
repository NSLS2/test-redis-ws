# Locust Stress Testing

Load testing for the Redis WebSocket streaming system.

## Running Tests

```bash
# Install dependencies
pixi install

# Run with web UI
pixi run locust -f writer_load_test.py --host http://localhost:8000

# Run headless (100 users, spawn 10/sec, run 60s)
pixi run locust -f writer_load_test.py --host http://localhost:8000 --headless -u 100 -r 10 -t 60s

# Run multiple test files together
pixi run locust -f locust/writer_load_test.py,locust/websocket_load_test.py --host http://localhost:8000

# Test against Kubernetes
kubectl port-forward service/test-redis-ws 8000:8000
pixi run locust -f writer_load_test.py --host http://localhost:8000
```
