# Redis Kubernetes Deployment

This directory contains Kubernetes manifests for deploying Redis.

## Files
- `redis-deployment.yaml` - Redis deployment with 1 replica
- `redis-service.yaml` - ClusterIP service exposing port 6379

## Deploy
```bash
kubectl apply -f .
```

## Test
```bash
# Connect to a netshoot container
kubectl run netshoot --image=nicolaka/netshoot --rm -it --restart=Never -- /bin/bash

# Test Redis connection from inside the container
echo -e "PING\r\n" | nc redis 6379
```