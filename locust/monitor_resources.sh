#!/bin/bash

# Resource Usage Monitor for Load Testing
# Single snapshot of Kubernetes resources - use with 'watch' command
# Usage: watch -n 5 ./monitor_resources.sh

set -e


# Function to monitor node resources
monitor_nodes() {
    echo "=== NODE METRICS ==="
    
    # Header with same format as pod metrics
    printf "%-30s %-12s %-8s %-10s %-12s %-8s %-10s\n" "NAME" "CPU(cores)" "%CPU" "CPU-LIMIT" "MEMORY(bytes)" "%MEM" "MEM-LIMIT"
    printf "%-30s %-12s %-8s %-10s %-12s %-8s %-10s\n" "----" "----------" "----" "---------" "-------------" "----" "---------"
    
    # Get node metrics and capacity
    kubectl get nodes --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null | while read node_name; do
        if [[ -n "$node_name" ]]; then
            # Get current usage
            cpu_usage=$(kubectl top nodes "$node_name" --no-headers 2>/dev/null | awk '{print $2}')
            mem_usage=$(kubectl top nodes "$node_name" --no-headers 2>/dev/null | awk '{print $4}')
            
            # Get node capacity (limits)
            cpu_capacity=$(kubectl get node "$node_name" -o jsonpath='{.status.capacity.cpu}' 2>/dev/null)
            mem_capacity=$(kubectl get node "$node_name" -o jsonpath='{.status.capacity.memory}' 2>/dev/null)
            
            # Calculate percentages from kubectl top output
            cpu_percent=$(kubectl top nodes "$node_name" --no-headers 2>/dev/null | awk '{print $3}')
            mem_percent=$(kubectl top nodes "$node_name" --no-headers 2>/dev/null | awk '{print $5}')
            
            # If no metrics available, show N/A
            if [[ -z "$cpu_usage" ]]; then
                cpu_usage="N/A"
                mem_usage="N/A"
                cpu_percent="N/A"
                mem_percent="N/A"
            fi
            
            # Convert CPU capacity to millicores for consistency
            if [[ -n "$cpu_capacity" ]]; then
                cpu_capacity="${cpu_capacity}000m"
            fi
            
            # Convert memory capacity from Ki to Mi
            if [[ -n "$mem_capacity" && "$mem_capacity" =~ Ki$ ]]; then
                mem_num=$(echo "$mem_capacity" | sed 's/Ki//')
                mem_mi=$((mem_num / 1024))
                mem_capacity="${mem_mi}Mi"
            fi
            
            printf "%-30s %-12s %-8s %-10s %-12s %-8s %-10s\n" "$node_name" "$cpu_usage" "$cpu_percent" "$cpu_capacity" "$mem_usage" "$mem_percent" "$mem_capacity"
        fi
    done
    echo
}

# Function to monitor pod resources
monitor_pods() {
    echo "=== POD METRICS ==="
    
    # Header with proper spacing
    printf "%-30s %-12s %-8s %-10s %-12s %-8s %-10s\n" "NAME" "CPU(cores)" "%CPU" "CPU-LIMIT" "MEMORY(bytes)" "%MEM" "MEM-LIMIT"
    printf "%-30s %-12s %-8s %-10s %-12s %-8s %-10s\n" "----" "----------" "----" "---------" "-------------" "----" "---------"
    
    # Process test-redis-ws pods
    kubectl get pods -l app=test-redis-ws --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null | while read pod_name; do
        if [[ -n "$pod_name" ]]; then
            # Get current usage
            cpu_usage=$(kubectl top pods "$pod_name" --no-headers 2>/dev/null | awk '{print $2}')
            mem_usage=$(kubectl top pods "$pod_name" --no-headers 2>/dev/null | awk '{print $3}')
            # Get limits
            cpu_limit=$(kubectl get pod "$pod_name" -o jsonpath='{.spec.containers[0].resources.limits.cpu}' 2>/dev/null)
            mem_limit=$(kubectl get pod "$pod_name" -o jsonpath='{.spec.containers[0].resources.limits.memory}' 2>/dev/null)
            
            # If no metrics available, show N/A
            if [[ -z "$cpu_usage" ]]; then
                cpu_usage="N/A"
                mem_usage="N/A"
            fi
            
            # Calculate CPU percentage
            cpu_percent="N/A"
            if [[ -n "$cpu_usage" && "$cpu_usage" != "N/A" && -n "$cpu_limit" ]]; then
                # Remove 'm' from cpu_usage and convert limit to millicores
                cpu_usage_num=$(echo "$cpu_usage" | sed 's/m//')
                cpu_limit_num=$(echo "$cpu_limit" | sed 's/m//')
                
                # Handle different CPU limit formats (e.g., "200m" vs "0.2")
                if [[ "$cpu_limit" =~ m$ ]]; then
                    cpu_limit_num=$(echo "$cpu_limit" | sed 's/m//')
                else
                    # Convert cores to millicores (e.g., 0.2 -> 200)
                    cpu_limit_num=$(echo "$cpu_limit * 1000" | bc -l 2>/dev/null | cut -d. -f1)
                fi
                
                if [[ -n "$cpu_usage_num" && -n "$cpu_limit_num" && "$cpu_limit_num" -gt 0 ]]; then
                    cpu_percent=$(echo "scale=1; $cpu_usage_num * 100 / $cpu_limit_num" | bc -l 2>/dev/null | cut -d. -f1)
                    cpu_percent="${cpu_percent}%"
                fi
            fi
            
            # Calculate Memory percentage
            mem_percent="N/A"
            if [[ -n "$mem_usage" && "$mem_usage" != "N/A" && -n "$mem_limit" ]]; then
                # Convert memory values to bytes for calculation
                mem_usage_bytes=$(echo "$mem_usage" | sed 's/[^0-9]//g')
                mem_limit_bytes=$(echo "$mem_limit" | sed 's/[^0-9]//g')
                
                # Handle memory units (Ki, Mi, Gi)
                if [[ "$mem_usage" =~ Ki$ ]]; then
                    mem_usage_bytes=$((mem_usage_bytes * 1024))
                elif [[ "$mem_usage" =~ Mi$ ]]; then
                    mem_usage_bytes=$((mem_usage_bytes * 1024 * 1024))
                elif [[ "$mem_usage" =~ Gi$ ]]; then
                    mem_usage_bytes=$((mem_usage_bytes * 1024 * 1024 * 1024))
                fi
                
                if [[ "$mem_limit" =~ Ki$ ]]; then
                    mem_limit_bytes=$((mem_limit_bytes * 1024))
                elif [[ "$mem_limit" =~ Mi$ ]]; then
                    mem_limit_bytes=$((mem_limit_bytes * 1024 * 1024))
                elif [[ "$mem_limit" =~ Gi$ ]]; then
                    mem_limit_bytes=$((mem_limit_bytes * 1024 * 1024 * 1024))
                fi
                
                if [[ -n "$mem_usage_bytes" && -n "$mem_limit_bytes" && "$mem_limit_bytes" -gt 0 ]]; then
                    mem_percent=$(echo "scale=1; $mem_usage_bytes * 100 / $mem_limit_bytes" | bc -l 2>/dev/null | cut -d. -f1)
                    mem_percent="${mem_percent}%"
                fi
            fi
            
            # Always show the pod, even if no metrics
            printf "%-30s %-12s %-8s %-10s %-12s %-8s %-10s\n" "$pod_name" "$cpu_usage" "$cpu_percent" "$cpu_limit" "$mem_usage" "$mem_percent" "$mem_limit"
        fi
    done
    
    # Process redis pods
    kubectl get pods -l app=redis --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null | while read pod_name; do
        if [[ -n "$pod_name" ]]; then
            # Get current usage
            cpu_usage=$(kubectl top pods "$pod_name" --no-headers 2>/dev/null | awk '{print $2}')
            mem_usage=$(kubectl top pods "$pod_name" --no-headers 2>/dev/null | awk '{print $3}')
            # Get limits
            cpu_limit=$(kubectl get pod "$pod_name" -o jsonpath='{.spec.containers[0].resources.limits.cpu}' 2>/dev/null)
            mem_limit=$(kubectl get pod "$pod_name" -o jsonpath='{.spec.containers[0].resources.limits.memory}' 2>/dev/null)
            
            # Calculate CPU percentage
            cpu_percent="N/A"
            if [[ -n "$cpu_usage" && -n "$cpu_limit" ]]; then
                # Remove 'm' from cpu_usage and convert limit to millicores
                cpu_usage_num=$(echo "$cpu_usage" | sed 's/m//')
                cpu_limit_num=$(echo "$cpu_limit" | sed 's/m//')
                
                # Handle different CPU limit formats (e.g., "200m" vs "0.2")
                if [[ "$cpu_limit" =~ m$ ]]; then
                    cpu_limit_num=$(echo "$cpu_limit" | sed 's/m//')
                else
                    # Convert cores to millicores (e.g., 0.2 -> 200)
                    cpu_limit_num=$(echo "$cpu_limit * 1000" | bc -l 2>/dev/null | cut -d. -f1)
                fi
                
                if [[ -n "$cpu_usage_num" && -n "$cpu_limit_num" && "$cpu_limit_num" -gt 0 ]]; then
                    cpu_percent=$(echo "scale=1; $cpu_usage_num * 100 / $cpu_limit_num" | bc -l 2>/dev/null | cut -d. -f1)
                    cpu_percent="${cpu_percent}%"
                fi
            fi
            
            # Calculate Memory percentage
            mem_percent="N/A"
            if [[ -n "$mem_usage" && -n "$mem_limit" ]]; then
                # Convert memory values to bytes for calculation
                mem_usage_bytes=$(echo "$mem_usage" | sed 's/[^0-9]//g')
                mem_limit_bytes=$(echo "$mem_limit" | sed 's/[^0-9]//g')
                
                # Handle memory units (Ki, Mi, Gi)
                if [[ "$mem_usage" =~ Ki$ ]]; then
                    mem_usage_bytes=$((mem_usage_bytes * 1024))
                elif [[ "$mem_usage" =~ Mi$ ]]; then
                    mem_usage_bytes=$((mem_usage_bytes * 1024 * 1024))
                elif [[ "$mem_usage" =~ Gi$ ]]; then
                    mem_usage_bytes=$((mem_usage_bytes * 1024 * 1024 * 1024))
                fi
                
                if [[ "$mem_limit" =~ Ki$ ]]; then
                    mem_limit_bytes=$((mem_limit_bytes * 1024))
                elif [[ "$mem_limit" =~ Mi$ ]]; then
                    mem_limit_bytes=$((mem_limit_bytes * 1024 * 1024))
                elif [[ "$mem_limit" =~ Gi$ ]]; then
                    mem_limit_bytes=$((mem_limit_bytes * 1024 * 1024 * 1024))
                fi
                
                if [[ -n "$mem_usage_bytes" && -n "$mem_limit_bytes" && "$mem_limit_bytes" -gt 0 ]]; then
                    mem_percent=$(echo "scale=1; $mem_usage_bytes * 100 / $mem_limit_bytes" | bc -l 2>/dev/null | cut -d. -f1)
                    mem_percent="${mem_percent}%"
                fi
            fi
            
            if [[ -n "$cpu_usage" ]]; then
                printf "%-30s %-12s %-8s %-10s %-12s %-8s %-10s\n" "$pod_name" "$cpu_usage" "$cpu_percent" "$cpu_limit" "$mem_usage" "$mem_percent" "$mem_limit"
            fi
        fi
    done
    
    echo
    echo "=== POD STATUS ==="
    kubectl get pods -l app=test-redis-ws --no-headers -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,RESTARTS:.status.containerStatuses[0].restartCount,AGE:.metadata.creationTimestamp
    kubectl get pods -l app=redis --no-headers -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,RESTARTS:.status.containerStatuses[0].restartCount,AGE:.metadata.creationTimestamp
    echo
}


# Function to monitor network connections
monitor_network() {
    echo "=== NETWORK METRICS ==="
    
    # Service summary with connection info
    printf "%-20s %-12s %-15s %-10s %-15s %-12s\n" "SERVICE" "TYPE" "CLUSTER-IP" "PORT" "NODEPORT" "CONNECTIONS"
    printf "%-20s %-12s %-15s %-10s %-15s %-12s\n" "-------" "----" "----------" "----" "--------" "-----------"
    
    # Get service info and format it properly
    local svc_name=$(kubectl get svc test-redis-ws -o jsonpath='{.metadata.name}' 2>/dev/null)
    local svc_type=$(kubectl get svc test-redis-ws -o jsonpath='{.spec.type}' 2>/dev/null)
    local cluster_ip=$(kubectl get svc test-redis-ws -o jsonpath='{.spec.clusterIP}' 2>/dev/null)
    local port=$(kubectl get svc test-redis-ws -o jsonpath='{.spec.ports[0].port}' 2>/dev/null)
    local nodeport=$(kubectl get svc test-redis-ws -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null)
    
    # Get Redis connection count as network activity indicator
    local redis_connections="N/A"
    local redis_pod=$(kubectl get pods -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [[ -n "$redis_pod" ]]; then
        redis_connections=$(kubectl exec "$redis_pod" -- redis-cli INFO clients 2>/dev/null | grep "connected_clients:" | cut -d: -f2 | tr -d '\r' || echo "N/A")
    fi
    
    if [[ -n "$svc_name" ]]; then
        # Handle empty nodeport for non-NodePort services
        [[ -z "$nodeport" || "$nodeport" == "null" ]] && nodeport="<none>"
        printf "%-20s %-12s %-15s %-10s %-15s %-12s\n" "$svc_name" "$svc_type" "$cluster_ip" "$port" "$nodeport" "$redis_connections"
    else
        echo "Failed to get service info"
    fi
    
    echo
    # Get network stats from all test-redis-ws pods
    echo "NETWORK ACTIVITY (per pod):"
    printf "%-30s %-10s %-10s\n" "POD" "RX (MB)" "TX (MB)"
    printf "%-30s %-10s %-10s\n" "---" "-------" "-------"
    
    kubectl get pods -l app=test-redis-ws --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null | while read pod_name; do
        if [[ -n "$pod_name" ]]; then
            # Get network interface stats from inside the pod
            local net_stats=$(kubectl exec "$pod_name" -- cat /proc/net/dev 2>/dev/null | grep eth0 || echo "")
            if [[ -n "$net_stats" ]]; then
                local rx_bytes=$(echo "$net_stats" | awk '{print $2}')
                local tx_bytes=$(echo "$net_stats" | awk '{print $10}')
                
                # Convert to MB for readability
                local rx_mb=$((rx_bytes / 1024 / 1024))
                local tx_mb=$((tx_bytes / 1024 / 1024))
                
                printf "%-30s %-10s %-10s\n" "$pod_name" "${rx_mb}" "${tx_mb}"
            else
                printf "%-30s %-10s %-10s\n" "$pod_name" "N/A" "N/A"
            fi
        fi
    done
    echo
}


# Main execution - single snapshot
monitor_nodes
monitor_pods
monitor_network