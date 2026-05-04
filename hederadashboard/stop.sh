#!/bin/bash
# Stop Hedera Dashboard

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.hederadashboard.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        rm -f "$PID_FILE"
        echo "[hedera] Stopped (PID $PID)"
    else
        rm -f "$PID_FILE"
        echo "[hedera] Not running (stale PID file removed)"
    fi
else
    echo "[hedera] Not running"
fi
