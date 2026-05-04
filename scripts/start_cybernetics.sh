#!/bin/bash
# Startup script for Cybernetics system
# Starts both sync daemon and Flask dashboard

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DASHBOARD_DIR="$PROJECT_ROOT/dashboard3"
LOGS_DIR="$PROJECT_ROOT/logs"
ROOT_VENV="$PROJECT_ROOT/venv"
DEPS_MARKER="$ROOT_VENV/.deps_installed"
SYNC_WORKER="$PROJECT_ROOT/scripts/sync_worker.py"
DASHBOARD_APP="$DASHBOARD_DIR/app.py"

log_warn() {
    echo "⚠️  $1"
}

systemd_dashboard_active() {
    command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet cyber-dashboard.service
}

find_existing_pid() {
    local pattern="$1"
    pgrep -f -- "$pattern" 2>/dev/null | head -n 1 || true
}

start_with_pidfile() {
    local name="$1"
    local pidfile="$2"
    local pattern="$3"
    shift 3

    if [ -f "$pidfile" ]; then
        local existing_pid
        existing_pid="$(cat "$pidfile" 2>/dev/null || true)"
        if [ -n "$existing_pid" ] && ps -p "$existing_pid" > /dev/null 2>&1; then
            echo "✅ $name already running (PID: $existing_pid)"
            return 0
        fi
        rm -f "$pidfile"
    fi

    local discovered_pid
    discovered_pid="$(find_existing_pid "$pattern")"
    if [ -n "$discovered_pid" ] && ps -p "$discovered_pid" > /dev/null 2>&1; then
        echo "$discovered_pid" > "$pidfile"
        echo "✅ $name already running (PID: $discovered_pid)"
        return 0
    fi

    nohup "$@" > "$LOGS_DIR/$(echo "$name" | tr ' ' '_' | tr '[:upper:]' '[:lower:]').log" 2>&1 &
    local new_pid=$!
    sleep 1

    if ! ps -p "$new_pid" > /dev/null 2>&1; then
        discovered_pid="$(find_existing_pid "$pattern")"
        if [ -n "$discovered_pid" ] && ps -p "$discovered_pid" > /dev/null 2>&1; then
            new_pid="$discovered_pid"
        else
            log_warn "$name failed to start; check $LOGS_DIR/$(echo "$name" | tr ' ' '_' | tr '[:upper:]' '[:lower:]').log"
            rm -f "$pidfile"
            return 0
        fi
    fi

    echo "$new_pid" > "$pidfile"
    echo "✅ $name started (PID: $new_pid)"
}

echo "========================================"
echo "Starting Cybernetics System"
echo "========================================"

# Create logs directory if it doesn't exist
mkdir -p "$LOGS_DIR"

if [ ! -f "$PROJECT_ROOT/.env" ]; then
    log_warn ".env file not found at $PROJECT_ROOT/.env (dashboard + sync will be skipped)"
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

# Ensure root venv + dependencies
if command -v python3 > /dev/null 2>&1; then
    if [ ! -d "$ROOT_VENV" ]; then
        echo "Creating root virtual environment..."
        python3 -m venv "$ROOT_VENV"
    fi

    if ! "$ROOT_VENV/bin/python3" -m pip --version > /dev/null 2>&1; then
        "$ROOT_VENV/bin/python3" -m ensurepip --upgrade
    fi

    if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
        if [ ! -f "$DEPS_MARKER" ]; then
            if "$ROOT_VENV/bin/python3" -m pip install -r "$PROJECT_ROOT/requirements.txt"; then
                touch "$DEPS_MARKER"
            else
                log_warn "Dependency install failed; continuing without updating packages."
            fi
        fi
    else
        log_warn "No requirements.txt found at $PROJECT_ROOT (skipping pip install)"
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
    SYNC_PYTHON="$ROOT_VENV/bin/python3"
    start_with_pidfile "Sync Daemon" "$LOGS_DIR/sync_daemon.pid" \
        "$SYNC_WORKER" \
        "$SYNC_PYTHON" "$SYNC_WORKER"
fi

if [ "${ENABLE_DASHBOARD:-0}" -eq 1 ]; then
    echo ""
    echo "Starting Flask Dashboard 3.0..."
    if systemd_dashboard_active; then
        echo "✅ Dashboard already managed by cyber-dashboard.service"
    else
        start_with_pidfile "Dashboard" "$LOGS_DIR/dashboard.pid" \
            "$DASHBOARD_APP" \
            "$ROOT_VENV/bin/python3" "$DASHBOARD_APP"
    fi
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
