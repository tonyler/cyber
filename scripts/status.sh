#!/bin/bash
# Check status of all Cybernetics services

set -euo pipefail

echo "========================================"
echo "Cybernetics System Status"
echo "========================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOGS_DIR="$PROJECT_ROOT/logs"

find_pid_by_pattern() {
    local pattern="$1"
    pgrep -f -- "$pattern" 2>/dev/null | head -n 1 || true
}

check_service() {
    local name="$1"
    local pidfile="$2"
    local logfile="$3"
    local pattern="$4"
    local url="${5:-}"
    local pid=""

    echo "$name:"
    if [ -f "$pidfile" ]; then
        pid="$(cat "$pidfile" 2>/dev/null || true)"
        if [ -n "$pid" ] && ps -p "$pid" > /dev/null 2>&1; then
            :
        else
            rm -f "$pidfile"
            pid=""
        fi
    fi

    if [ -z "$pid" ] && [ -n "$pattern" ]; then
        pid="$(find_pid_by_pattern "$pattern")"
        if [ -n "$pid" ] && ps -p "$pid" > /dev/null 2>&1; then
            echo "$pid" > "$pidfile"
        else
            pid=""
        fi
    fi

    if [ -n "$pid" ]; then
        echo "  ✅ Running (PID: $pid)"
        if [ -n "$url" ]; then
            echo "  URL: $url"
        fi
        if [ -n "$logfile" ]; then
            echo "  Log: $logfile"
        fi
    else
        echo "  ❌ Not running"
    fi
    echo ""
}

check_service "Discord Bot" "$LOGS_DIR/bot.pid" "$LOGS_DIR/bot.log" "bot.py"
check_service "Scrapers Daemon" "$LOGS_DIR/scrapers.pid" "$LOGS_DIR/scrapers.log" "$PROJECT_ROOT/scripts/scraper_daemon.sh"
check_service "Dashboard" "$LOGS_DIR/dashboard.pid" "$LOGS_DIR/dashboard.log" "$PROJECT_ROOT/dashboard3/app.py" "http://localhost:5002"
check_service "Sync Daemon" "$LOGS_DIR/sync_daemon.pid" "$LOGS_DIR/sync_daemon.log" "$PROJECT_ROOT/scripts/sync_worker.py"
check_service "Monthly Views Daemon" "$LOGS_DIR/monthly_views.pid" "$LOGS_DIR/monthly_views.log" "$PROJECT_ROOT/scripts/view_snapshot_daemon.sh"

echo "========================================"
