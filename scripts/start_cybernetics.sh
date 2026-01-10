#!/bin/bash
# Startup script for Cybernetics system
# Starts both sync daemon and Flask dashboard

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DASHBOARD_DIR="$PROJECT_ROOT/dashboard"
LOGS_DIR="$PROJECT_ROOT/logs"
VENV_DIR="$DASHBOARD_DIR/venv"
SYNC_VENV_DIR="$PROJECT_ROOT/venv"
SYNC_WORKER="$PROJECT_ROOT/scripts/sync_worker.py"
DASHBOARD_APP="$DASHBOARD_DIR/app.py"
INIT_DBS="$PROJECT_ROOT/scripts/init_dbs.py"

log_warn() {
    echo "⚠️  $1"
}

start_with_pidfile() {
    local name="$1"
    local pidfile="$2"
    shift 2

    if [ -f "$pidfile" ]; then
        local existing_pid
        existing_pid="$(cat "$pidfile" 2>/dev/null || true)"
        if [ -n "$existing_pid" ] && ps -p "$existing_pid" > /dev/null 2>&1; then
            echo "✅ $name already running (PID: $existing_pid)"
            return 0
        fi
        rm -f "$pidfile"
    fi

    nohup "$@" > "$LOGS_DIR/$(echo "$name" | tr ' ' '_' | tr '[:upper:]' '[:lower:]').log" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$pidfile"
    echo "✅ $name started (PID: $new_pid)"
}

echo "========================================"
echo "Starting Cybernetics System"
echo "========================================"

# Create logs directory if it doesn't exist
mkdir -p "$LOGS_DIR"

if [ ! -f "$DASHBOARD_DIR/.env" ]; then
    log_warn ".env file not found at $DASHBOARD_DIR/.env (dashboard + sync will be skipped)"
    ENABLE_DASHBOARD=0
else
    ENABLE_DASHBOARD=1
fi

if [ ! -f "$DASHBOARD_APP" ]; then
    log_warn "Dashboard app not found at $DASHBOARD_APP"
    ENABLE_DASHBOARD=0
fi

if [ ! -f "$SYNC_WORKER" ]; then
    log_warn "Sync worker not found at $SYNC_WORKER"
    ENABLE_SYNC=0
else
    ENABLE_SYNC=1
fi

if [ "$ENABLE_DASHBOARD" -eq 0 ] && [ "$ENABLE_SYNC" -eq 0 ]; then
    log_warn "Nothing to start (missing dashboard/sync entrypoints)."
    exit 0
fi

# Ensure dashboard venv + dependencies
if command -v python3 > /dev/null 2>&1; then
    if [ ! -d "$VENV_DIR" ]; then
        echo "Creating dashboard virtual environment..."
        python3 -m venv "$VENV_DIR"
    fi

    req_args=()
    if [ -f "$DASHBOARD_DIR/requirements.txt" ]; then
        req_args+=(-r "$DASHBOARD_DIR/requirements.txt")
    fi
    if [ -f "$DASHBOARD_DIR/requirements-sync.txt" ]; then
        req_args+=(-r "$DASHBOARD_DIR/requirements-sync.txt")
    fi

    if [ "${#req_args[@]}" -gt 0 ]; then
        "$VENV_DIR/bin/pip" install "${req_args[@]}"
    else
        log_warn "No requirements files found in $DASHBOARD_DIR (skipping pip install)"
    fi
else
    log_warn "python3 not found; dashboard + sync cannot start"
    ENABLE_DASHBOARD=0
    ENABLE_SYNC=0
fi

# Ensure CSV storage directory exists
CSV_DIR="$PROJECT_ROOT/database"
mkdir -p "$CSV_DIR"
if [ ! -f "$CSV_DIR/members.csv" ] || [ ! -f "$CSV_DIR/links.csv" ]; then
    echo "⚠️  CSV storage not found. Creating empty CSVs..."
    touch "$CSV_DIR/members.csv" "$CSV_DIR/links.csv"
fi

if [ "${ENABLE_SYNC:-0}" -eq 1 ]; then
    echo ""
    echo "Starting Sync Daemon..."
    SYNC_PYTHON="$VENV_DIR/bin/python3"
    if [ -x "$SYNC_VENV_DIR/bin/python3" ]; then
        SYNC_PYTHON="$SYNC_VENV_DIR/bin/python3"
    fi
    start_with_pidfile "Sync Daemon" "$LOGS_DIR/sync_daemon.pid" \
        "$SYNC_PYTHON" "$SYNC_WORKER"
fi

if [ "${ENABLE_DASHBOARD:-0}" -eq 1 ]; then
    echo ""
    echo "Starting Flask Dashboard (Cyberpunk UI + Stats DB)..."
    start_with_pidfile "Dashboard" "$LOGS_DIR/dashboard.pid" \
        "$VENV_DIR/bin/python3" "$DASHBOARD_APP"
fi

echo ""
echo "========================================"
echo "✅ Cybernetics System Started"
echo "========================================"
if [ -f "$LOGS_DIR/sync_daemon.pid" ]; then
    echo "Sync Daemon PID: $(cat "$LOGS_DIR/sync_daemon.pid" 2>/dev/null || true)"
fi
if [ -f "$LOGS_DIR/dashboard.pid" ]; then
    echo "Dashboard PID: $(cat "$LOGS_DIR/dashboard.pid" 2>/dev/null || true)"
fi
echo ""
echo "Dashboard URL: http://localhost:5002"
echo ""
echo "Logs:"
echo "  Sync: $LOGS_DIR/sync_daemon.log"
echo "  Dashboard: $LOGS_DIR/dashboard.log"
echo ""
echo "To stop: ./scripts/stop_all.sh"
echo "========================================"
