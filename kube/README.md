# Kubernetes Deployments

This directory contains Kubernetes manifests for deploying Redis and the test-redis-ws application.

## Files
- `redis-deployment.yaml` - Redis deployment with 1 replica
- `redis-service.yaml` - ClusterIP service exposing Redis on port 6379
- `test-redis-ws-deployment.yaml` - test-redis-ws deployment with 3 replicas
- `test-redis-ws-service.yaml` - ClusterIP service exposing test-redis-ws on port 8000

## Deploy
```bash
# Deploy everything
kubectl apply -f .

# Or deploy individually
kubectl apply -f redis-deployment.yaml
kubectl apply -f redis-service.yaml
kubectl apply -f test-redis-ws-deployment.yaml
kubectl apply -f test-redis-ws-service.yaml
```

## Container Image
The test-redis-ws image is automatically built and pushed to GitHub Container Registry on push to main branch.
- Image: `ghcr.io/nsls2/test-redis-ws:latest`
- Build workflow: `.github/workflows/build-push.yml`

## Test Redis
```bash
# Connect to a netshoot container
kubectl run netshoot --image=nicolaka/netshoot --rm -it --restart=Never -- /bin/bash

# Test Redis connection from inside the container
echo -e "PING\r\n" | nc redis 6379
```

## Test test-redis-ws
```bash
# Connect to a netshoot container
kubectl run netshoot --image=nicolaka/netshoot --rm -it --restart=Never -- /bin/bash

# Test the service from inside the container
curl http://test-redis-ws:8000/
```