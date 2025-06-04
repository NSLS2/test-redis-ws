#/bin/bash

echo "Testing subscriptions..."

# Scale deployments
echo "Scaling deployments..."
kubectl scale deployment test-redis-ws --replicas=3 streaming-client --replicas=3

# Restart writer job
echo "Starting writer job..."
kubectl delete job writing-client 2>/dev/null
kubectl apply -f writing.yaml

# Wait for pods
echo "Waiting for pods..."
kubectl wait --for=condition=ready pod -l streaming=true --timeout=60s

# Collect logs from all streaming pods
echo "Collecting logs for 20 seconds..."
kubectl logs -l streaming=true -f --prefix=true --timestamps=true --max-log-requests=10 > subscription.log 2>&1 &
LOG_PID=$!

# Let test run
sleep 20
kill $LOG_PID 2>/dev/null

echo -e "\nLog collection complete. Results saved to: subscription.log"
