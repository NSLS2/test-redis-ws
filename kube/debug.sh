#!/bin/bash

echo "=== test-redis-ws pod logs ==="
kubectl logs -l app=test-redis-ws --tail=20

echo -e "\n=== Redis pod status ==="
kubectl get pods -l app=redis

echo -e "\n=== Test Redis connection from test-redis-ws pod ==="
POD=$(kubectl get pods -l app=test-redis-ws -o jsonpath='{.items[0].metadata.name}')
kubectl exec $POD -- python -c "import redis; r = redis.from_url('redis://redis:6379/0'); print('Redis ping:', r.ping())" 2>&1 || echo "Failed to connect to Redis"