# Kubernetes Deployments

## Files
- `server.yaml` - Redis + test-redis-ws server (3 replicas)
- `streaming.yaml` - Streaming clients (3 replicas)
- `writing.yaml` - Writing clients (3 replicas)

## Deploy
```bash
kubectl apply -f server.yaml
kubectl apply -f streaming.yaml
kubectl apply -f writing.yaml
```

## Test
```bash
# From netshoot container
kubectl run netshoot --image=nicolaka/netshoot --rm -it --restart=Never -- /bin/bash

# Test Redis
echo -e "PING\r\n" | nc redis 6379

# Test API
curl http://test-redis-ws:8000/
```

## Images
Built automatically via GitHub Actions:
- `ghcr.io/nsls2/test-redis-ws:kube`
- `ghcr.io/nsls2/streaming-client:kube`
- `ghcr.io/nsls2/writing-client:kube`