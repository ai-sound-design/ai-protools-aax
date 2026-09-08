#!/bin/bash

# Combined Memory Monitoring + Profiling Script
# Monitors container RAM over time AND profiles Python memory usage

CONTAINER_NAME="mmaudio-api"
MONITOR_LOG="logs/memory_monitor_$(date +%Y%m%d_%H%M%S).log"
PROFILE_LOG="logs/memory_profiles_$(date +%Y%m%d_%H%M%S).log"
INTERVAL=300  # 5 minutes

echo "=========================================="
echo "  MMAudio API Memory Leak Detector"
echo "=========================================="
echo "Container: $CONTAINER_NAME"
echo "Interval: ${INTERVAL}s (5 minutes)"
echo "Monitor Log: $MONITOR_LOG"
echo "Profile Log: $PROFILE_LOG"
echo ""
echo "This will:"
echo "  1. Track overall container RAM usage"
echo "  2. Profile Python object memory usage"
echo "  3. Identify memory allocation sources"
echo ""
echo "Press Ctrl+C to stop monitoring"
echo "=========================================="
echo ""

# Create headers
echo "timestamp,elapsed_seconds,container_mem_mb,container_mem_percent,python_rss_mb,python_vsz_mb,python_cpu_percent,python_mem_percent" > "$MONITOR_LOG"
echo "Monitoring started at $(date)" >> "$PROFILE_LOG"
echo "" >> "$PROFILE_LOG"

START_TIME=$(date +%s)
ITERATION=0

while true; do
    ITERATION=$((ITERATION + 1))
    CURRENT_TIME=$(date +%s)
    ELAPSED=$((CURRENT_TIME - START_TIME))
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    
    echo "----------------------------------------"
    echo "[$TIMESTAMP] Iteration $ITERATION (Elapsed: ${ELAPSED}s)"
    echo "----------------------------------------"
    
    # 1. Get container memory stats
    CONTAINER_STATS=$(docker stats $CONTAINER_NAME --no-stream --format "{{.MemUsage}},{{.MemPerc}}" 2>/dev/null)
    
    if [ -z "$CONTAINER_STATS" ]; then
        echo "ERROR: Container not running"
        break
    fi
    
    # Parse container stats
    CONTAINER_MEM_RAW=$(echo "$CONTAINER_STATS" | cut -d',' -f1 | cut -d'/' -f1)
    CONTAINER_MEM_PCT=$(echo "$CONTAINER_STATS" | cut -d',' -f2 | sed 's/%//g' | tr ',' '.')
    
    # Convert to MB
    if echo "$CONTAINER_MEM_RAW" | grep -q "GiB"; then
        CONTAINER_MEM=$(echo "$CONTAINER_MEM_RAW" | sed 's/GiB//g' | tr ',' '.' | awk '{printf "%.2f", $1 * 1024}')
    elif echo "$CONTAINER_MEM_RAW" | grep -q "MiB"; then
        CONTAINER_MEM=$(echo "$CONTAINER_MEM_RAW" | sed 's/MiB//g' | tr ',' '.')
    else
        CONTAINER_MEM="0"
    fi
    
    # 2. Get Python process stats (match both "python3 main.py" and "python3 -u main.py")
    PYTHON_STATS=$(docker exec $CONTAINER_NAME ps aux | grep "python3.*main.py" | grep -v grep | awk '{print $3","$4","$5","$6}' 2>/dev/null)
    
    if [ -z "$PYTHON_STATS" ]; then
        echo "WARNING: Python process not found"
        PYTHON_CPU="0.0"
        PYTHON_MEM_PCT="0.0"
        PYTHON_VSZ="0"
        PYTHON_RSS="0"
        PYTHON_RSS_MB="0.00"
        PYTHON_VSZ_MB="0.00"
    else
        PYTHON_CPU=$(echo "$PYTHON_STATS" | cut -d',' -f1 | tr ',' '.')
        PYTHON_MEM_PCT=$(echo "$PYTHON_STATS" | cut -d',' -f2 | tr ',' '.')
        PYTHON_VSZ=$(echo "$PYTHON_STATS" | cut -d',' -f3)
        PYTHON_RSS=$(echo "$PYTHON_STATS" | cut -d',' -f4)
        
        PYTHON_RSS_MB=$(echo "scale=2; $PYTHON_RSS / 1024" | bc)
        PYTHON_VSZ_MB=$(echo "scale=2; $PYTHON_VSZ / 1024" | bc)
    fi
    
    # Log to CSV
    echo "$TIMESTAMP,$ELAPSED,$CONTAINER_MEM,$CONTAINER_MEM_PCT,$PYTHON_RSS_MB,$PYTHON_VSZ_MB,$PYTHON_CPU,$PYTHON_MEM_PCT" >> "$MONITOR_LOG"
    
    # Print summary
    printf "Container Memory: %8.2f MB (%5.2f%%)\n" "$CONTAINER_MEM" "$CONTAINER_MEM_PCT"
    printf "Python RSS:       %8.2f MB (%5.2f%%)\n" "$PYTHON_RSS_MB" "$PYTHON_MEM_PCT"
    echo ""
    
    # 3. Run detailed memory profiling
    echo "Running memory profiler..."
    echo "========================================" >> "$PROFILE_LOG"
    echo "Iteration $ITERATION - $TIMESTAMP (Elapsed: ${ELAPSED}s)" >> "$PROFILE_LOG"
    echo "Container: ${CONTAINER_MEM} MB | Python: ${PYTHON_RSS_MB} MB" >> "$PROFILE_LOG"
    echo "========================================" >> "$PROFILE_LOG"
    
    docker exec $CONTAINER_NAME python3 /workspace/protools-aax/standalone-API/memory_profiler.py >> "$PROFILE_LOG" 2>&1
    echo "" >> "$PROFILE_LOG"
    echo "" >> "$PROFILE_LOG"
    
    # 4. Get API memory endpoint
    echo "Fetching /memory/profile endpoint..."
    PROFILE_JSON=$(curl -s http://localhost:8000/memory/profile 2>/dev/null)
    
    if [ ! -z "$PROFILE_JSON" ]; then
        echo "API Memory Profile:" >> "$PROFILE_LOG"
        echo "$PROFILE_JSON" | python3 -m json.tool >> "$PROFILE_LOG" 2>/dev/null || echo "$PROFILE_JSON" >> "$PROFILE_LOG"
        echo "" >> "$PROFILE_LOG"
    fi
    
    echo "✓ Profiling complete"
    echo ""
    echo "Next check in ${INTERVAL}s..."
    echo ""
    
    sleep $INTERVAL
done

echo ""
echo "=========================================="
echo "Monitoring stopped"
echo "=========================================="
echo "Results saved to:"
echo "  - Monitor CSV: $MONITOR_LOG"
echo "  - Profile Log: $PROFILE_LOG"
echo "=========================================="
