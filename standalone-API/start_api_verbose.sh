#!/bin/bash
# Persistent API Startup Script with Logging

cd /workspace/protools-aax/standalone-API

# Create logs directory
mkdir -p logs

# Generate log filename with timestamp
LOG_FILE="logs/api_$(date +%Y%m%d_%H%M%S).log"

echo "=========================================="
echo "Starting MMAudio Standalone API"
echo "Log file: $LOG_FILE"
echo "=========================================="
echo ""

# Start with logging to file AND stdout (using tee)
# -u flag ensures unbuffered output (real-time logging)
python3 -u main.py 2>&1 | tee "$LOG_FILE"