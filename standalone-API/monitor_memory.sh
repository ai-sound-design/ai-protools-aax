#!/bin/bash

# Memory monitoring script for MMAudio API
# Tracks RAM usage over time to identify memory leaks

CONTAINER_NAME="mmaudio-api"
LOG_FILE="logs/memory_monitor_$(date +%Y%m%d_%H%M%S).log"
INTERVAL=1800  # Check every 30 minutes (1800 seconds)

echo "Starting memory monitoring for container: $CONTAINER_NAME"
echo "Logging to: $LOG_FILE"
echo "Check interval: ${INTERVAL}s"
echo ""

# Create header
echo "timestamp,elapsed_seconds,container_mem_mb,container_mem_percent,python_rss_mb,python_vsz_mb,python_cpu_percent,python_mem_percent" > "$LOG_FILE"

START_TIME=$(date +%s)

while true; do
    CURRENT_TIME=$(date +%s)
    ELAPSED=$((CURRENT_TIME - START_TIME))
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    
    # Get container memory stats
    CONTAINER_STATS=$(docker stats $CONTAINER_NAME --no-stream --format "{{.MemUsage}},{{.MemPerc}}" 2>/dev/null)
    
    if [ -z "$CONTAINER_STATS" ]; then
        echo "[$TIMESTAMP] ERROR: Container not running"
        break
    fi
    
    # Parse container stats (format: "123.4MiB / 456.7MiB,12.34%")
    CONTAINER_MEM=$(echo "$CONTAINER_STATS" | cut -d',' -f1 | cut -d'/' -f1 | sed 's/[^0-9.]//g')
    CONTAINER_MEM_PCT=$(echo "$CONTAINER_STATS" | cut -d',' -f2 | sed 's/%//g')
    
    # Convert to MB if in GiB
    if echo "$CONTAINER_STATS" | grep -q "GiB"; then
        CONTAINER_MEM=$(echo "$CONTAINER_MEM * 1024" | bc)
    fi
    
    # Get Python process stats inside container
    PYTHON_STATS=$(docker exec $CONTAINER_NAME ps aux | grep "python3 -u main.py" | grep -v grep | awk '{print $3","$4","$5","$6}' 2>/dev/null)
    
    if [ -z "$PYTHON_STATS" ]; then
        echo "[$TIMESTAMP] WARNING: Python process not found"
        PYTHON_CPU="0"
        PYTHON_MEM_PCT="0"
        PYTHON_VSZ="0"
        PYTHON_RSS="0"
    else
        PYTHON_CPU=$(echo "$PYTHON_STATS" | cut -d',' -f1)
        PYTHON_MEM_PCT=$(echo "$PYTHON_STATS" | cut -d',' -f2)
        PYTHON_VSZ=$(echo "$PYTHON_STATS" | cut -d',' -f3)
        PYTHON_RSS=$(echo "$PYTHON_STATS" | cut -d',' -f4)
        
        # Convert RSS and VSZ from KB to MB
        PYTHON_RSS_MB=$(echo "scale=2; $PYTHON_RSS / 1024" | bc)
        PYTHON_VSZ_MB=$(echo "scale=2; $PYTHON_VSZ / 1024" | bc)
    fi
    
    # Log to file
    echo "$TIMESTAMP,$ELAPSED,$CONTAINER_MEM,$CONTAINER_MEM_PCT,$PYTHON_RSS_MB,$PYTHON_VSZ_MB,$PYTHON_CPU,$PYTHON_MEM_PCT" >> "$LOG_FILE"
    
    # Print to console
    printf "[%s] Elapsed: %4ds | Container: %8.2f MB (%5.2f%%) | Python RSS: %8.2f MB (%5.2f%%)\n" \
        "$TIMESTAMP" "$ELAPSED" "$CONTAINER_MEM" "$CONTAINER_MEM_PCT" "$PYTHON_RSS_MB" "$PYTHON_MEM_PCT"
    
    sleep $INTERVAL
done

echo ""
echo "Monitoring stopped. Log saved to: $LOG_FILE"
