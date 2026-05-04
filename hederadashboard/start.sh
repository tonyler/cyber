#!/bin/bash
# Start Hedera Dashboard

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PID_FILE="$SCRIPT_DIR/.hederadashboard.pid"
LOG_FILE="$PROJECT_ROOT/logs/hederadashboard.log"

mkdir -p "$PROJECT_ROOT/logs"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "[hedera] Already running (PID $PID)"
        exit 0
    fi
    rm -f "$PID_FILE"
fi

cd "$SCRIPT_DIR"

VENV="$PROJECT_ROOT/venv"
if [ -d "$VENV" ]; then
    source "$VENV/bin/activate"
fi

nohup python app.py >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "[hedera] Started on port 5003 (PID $!)"
