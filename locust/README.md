# Locust Stress Testing

Load testing for the Redis WebSocket streaming system.

## Running Tests

```bash
# Install dependencies
pixi install

# Run with web UI (equal distribution of writers and streamers)
pixi run locust -f mixed_load_test.py --host http://localhost:8000

# Run headless (100 users, spawn 10/sec, run 60s)
pixi run locust -f mixed_load_test.py --host http://localhost:8000 --headless -u 100 -r 10 -t 60s

# Run with weighted distribution (70% writers, 30% websocket)
WRITER_WEIGHT=70 STREAMING_WEIGHT=30 pixi run locust -f locust/mixed_load_test.py --host http://localhost:8000

# Run with 1 writer and 10 streaming users
WRITER_WEIGHT=1 STREAMING_WEIGHT=10 pixi run locust -f locust/mixed_load_test.py --host http://localhost:8000

# Run with different ratio (4:1)
WRITER_WEIGHT=4 STREAMING_WEIGHT=1 pixi run locust -f locust/mixed_load_test.py --host http://localhost:8000

# Control logging verbosity (default is INFO)
pixi run locust -f locust/mixed_load_test.py --host http://localhost:8000 --loglevel WARNING
pixi run locust -f locust/mixed_load_test.py --host http://localhost:8000 -L ERROR

# Run end-to-end latency test (measures write to WebSocket delivery time)
pixi run locust -f locust/e2e_latency_test.py --host http://localhost:8000

# Test against Kubernetes

# First, deploy test-redis-ws to Kubernetes
kubectl apply -f ../kube/server.yaml

# Scale the deployment (optional - default is 3 replicas)
kubectl scale deployment test-redis-ws --replicas=5

# Port forward to access the service
kubectl port-forward service/test-redis-ws 8000:8000

# Run Locust tests
pixi run locust -f mixed_load_test.py --host http://localhost:8000
```

# Useful Redis commands
```
# Check Redis contents
kubectl exec $(kubectl get pods -l app=redis -o jsonpath='{.items[0].metadata.name}') -- redis-cli KEYS '*'

# Get value of a specific key (e.g., data:481980:0)
kubectl exec $(kubectl get pods -l app=redis -o jsonpath='{.items[0].metadata.name}') -- redis-cli HGETALL data:481980:0

# Clear Redis
kubectl exec $(kubectl get pods -l app=redis -o jsonpath='{.items[0].metadata.name}') -- redis-cli FLUSHALL
```

## Logging Configuration

By default, Locust logs to stderr with INFO level.

```bash
# Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
pixi run locust -f mixed_load_test.py --host http://localhost:8000 --loglevel INFO

# Write logs to file (default: stderr)
pixi run locust -f mixed_load_test.py --host http://localhost:8000 --logfile locust.log

# Both log level and file
pixi run locust -f mixed_load_test.py --host http://localhost:8000 --loglevel DEBUG --logfile debug.log
```
