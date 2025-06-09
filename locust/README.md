# Locust Load Testing

Load testing for the Redis WebSocket streaming system with mixed writer/streaming users.

## Quick Start

```bash
pixi install
pixi run locust -f mixed_load_test.py --host http://localhost:8000
```

## User Types

- **WriterUser**: Posts binary data to `/upload/{node_id}` endpoints
- **StreamingUser**: Connects via WebSocket to stream data and measure latency

## Configuration

Control user distribution with environment variables:

```bash
# 1 writer, 10 streaming users (default weights are 1:1)
WRITER_WEIGHT=1 STREAMING_WEIGHT=10 pixi run locust -f mixed_load_test.py --host http://localhost:8000

# Headless mode (100 users, 10/sec spawn rate, 60s duration)
pixi run locust -f mixed_load_test.py --host http://localhost:8000 --headless -u 100 -r 10 -t 60s

# Reduce logging noise
pixi run locust -f mixed_load_test.py --host http://localhost:8000 -L WARNING
```

## Kubernetes Testing

```bash
kubectl apply -f ../kube/server.yaml
kubectl port-forward service/test-redis-ws 8000:8000
pixi run locust -f mixed_load_test.py --host http://localhost:8000
```

## Redis Commands

```bash
# Check Redis contents
kubectl exec $(kubectl get pods -l app=redis -o jsonpath='{.items[0].metadata.name}') -- redis-cli KEYS '*'

# Clear Redis
kubectl exec $(kubectl get pods -l app=redis -o jsonpath='{.items[0].metadata.name}') -- redis-cli FLUSHALL
```
