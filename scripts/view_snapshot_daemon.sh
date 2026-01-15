#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ROOT_VENV="$PROJECT_ROOT/venv"
LOGS_DIR="$PROJECT_ROOT/logs"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_VENV/bin/python3}"
SNAPSHOT_SCRIPTS=(
    "$PROJECT_ROOT/scripts/monthly_views_snapshot.py"
    "$PROJECT_ROOT/scripts/monthly_actions_snapshot.py"
)
LOG_FILE="$LOGS_DIR/monthly_views.log"

RUN_PID=0
SLEEP_PID=0

cleanup() {
    set +e
    if [ "$RUN_PID" -ne 0 ]; then
        kill "$RUN_PID" 2>/dev/null || true
    fi
    if [ "$SLEEP_PID" -ne 0 ]; then
        kill "$SLEEP_PID" 2>/dev/null || true
    fi
    exit 0
}

trap cleanup TERM INT

run_snapshot() {
    for script in "${SNAPSHOT_SCRIPTS[@]}"; do
        "$PYTHON_BIN" "$script" >> "$LOG_FILE" 2>&1 &
        RUN_PID=$!
        wait "$RUN_PID"
        RUN_PID=0
    done
}

next_midnight() {
    local now next
    now="$(date -u +%s)"
    next="$(date -u -d "tomorrow 00:00" +%s)"
    echo $((next - now + 5))
}

sleep_until_midnight() {
    local duration
    duration="$(next_midnight)"
    if [ "$duration" -le 0 ]; then
        return
    fi
    sleep "$duration" &
    SLEEP_PID=$!
    wait "$SLEEP_PID"
    SLEEP_PID=0
}

mkdir -p "$LOGS_DIR"

while true; do
    run_snapshot
    sleep_until_midnight
done
