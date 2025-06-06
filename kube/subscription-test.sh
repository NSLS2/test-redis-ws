#/bin/bash

echo "Testing subscriptions..."
kubectl delete -f .
echo "Waiting 20s for deletion..."
sleep 20

# Ensure deployments exist
echo "Applying deployments..."
kubectl apply -f server.yaml
kubectl apply -f streaming.yaml

# Scale deployments
echo "Scaling deployments..."
kubectl scale deployment test-redis-ws --replicas=3 streaming-client --replicas=3

echo "Waiting 20s for server and clients to start..."
sleep 20

# NOW start writer job after everything else is ready
echo "Starting writer job..."
kubectl delete job writing-client 2>/dev/null
kubectl apply -f writing.yaml

# Wait for writer job pods to start
echo "Waiting for writer job to start..."
sleep 5

# Collect logs from all streaming pods
echo "Collecting logs for 20 seconds..."
kubectl logs -l streaming=true -f --prefix=true --timestamps=true --max-log-requests=10 > subscription.log 2>&1 &
LOG_PID=$!

sleep 20
kill $LOG_PID 2>/dev/null

echo -e "\nLog collection complete. Results saved to: subscription.log"
