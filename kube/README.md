# Kubernetes Deployments

## Files
- `server.yaml` - Redis + test-redis-ws server (3 replicas)
- `streaming.yaml` - Streaming clients (3 replicas)
- `writing.yaml` - Writing clients (3 replicas)

## Start fresh
```bash
kubectl delete -f .
```

## Deploy
```bash
kubectl apply -f server.yaml
kubectl apply -f streaming.yaml
kubectl apply -f writing.yaml
```

## Run the Writer Job
See https://kubernetes.io/docs/concepts/workloads/controllers/job/

```bash
# The Writers will be cleaned up automatically 60s after completion. You can delete it explicitly like this:
kubectl delete job writing-client

# Start the job.
kubectl apply -f writing.yaml
```

## Useful commands
```bash
# From netshoot container
kubectl run netshoot --image=nicolaka/netshoot --rm -it --restart=Never -- /bin/bash

# Test Redis
echo -e "PING\r\n" | nc redis 6379

# Test API
curl http://test-redis-ws:8000/

# Check Redis contents
kubectl exec $(kubectl get pods -l app=redis -o jsonpath='{.items[0].metadata.name}') -- redis-cli KEYS '*'

# Get value of a specific key (e.g., data:481980:0)
kubectl exec $(kubectl get pods -l app=redis -o jsonpath='{.items[0].metadata.name}') -- redis-cli HGETALL data:481980:0

# Clear Redis
kubectl exec $(kubectl get pods -l app=redis -o jsonpath='{.items[0].metadata.name}') -- redis-cli FLUSHALL

# Get streaming client logs
kubectl logs -l app=streaming-client -f --prefix=true --timestamps=true

# Get server logs
kubectl logs -l app=test-redis-ws -f --prefix=true --timestamps=true

# Get writer logs
kubectl logs -l app=writing-client -f --prefix=true --timestamps=true

# Get all logs
kubectl logs -l streaming=true -f --prefix=true --timestamps=true --max-log-requests 9
```

## Images
Built automatically via GitHub Actions:
- `ghcr.io/nsls2/test-redis-ws:kube`
- `ghcr.io/nsls2/streaming-client:kube`
- `ghcr.io/nsls2/writing-client:kube`
