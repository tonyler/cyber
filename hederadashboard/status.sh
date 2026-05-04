#!/bin/bash
# Status Hedera Dashboard

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.hederadashboard.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "[hedera] Running on port 5003 (PID $PID)"
    else
        echo "[hedera] Not running (stale PID file)"
    fi
else
    echo "[hedera] Not running"
fi
