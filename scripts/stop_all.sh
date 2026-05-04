#!/bin/bash
# Stop full Cybernetics stack: dashboard, sync daemon, Discord bot, scrapers.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOGS_DIR="$PROJECT_ROOT/logs"

# Kill all processes matching a pattern AND clean up the pidfile.
# Usage: kill_service <name> <pidfile> <pgrep-pattern>
kill_service() {
    local name="$1" pidfile="$2" pattern="$3"
    local killed=0

    # Kill by PID file first
    if [ -f "$pidfile" ]; then
        local pid
        pid="$(cat "$pidfile" 2>/dev/null || true)"
        if [ -n "$pid" ] && ps -p "$pid" > /dev/null 2>&1; then
            kill "$pid" 2>/dev/null || true
            killed=1
        fi
        rm -f "$pidfile"
    fi

    # Kill any remaining processes by pattern (handles orphans & stale PIDs)
    local pids
    pids="$(pgrep -f -- "$pattern" 2>/dev/null || true)"
    for pid in $pids; do
        if ps -p "$pid" > /dev/null 2>&1; then
            kill "$pid" 2>/dev/null || true
            killed=1
        fi
    done

    if [ "$killed" -eq 0 ]; then
        echo "  $name was not running"
        return
    fi

    # Wait up to 5s for clean exit
    local waited=0
    while [ "$waited" -lt 5 ]; do
        pids="$(pgrep -f -- "$pattern" 2>/dev/null || true)"
        [ -z "$pids" ] && break
        sleep 1
        waited=$((waited + 1))
    done

    # Force-kill anything still alive
    pids="$(pgrep -f -- "$pattern" 2>/dev/null || true)"
    for pid in $pids; do
        kill -9 "$pid" 2>/dev/null || true
    done

    echo "✅ $name stopped"
}

echo "========================================"
echo "Stopping Full Cybernetics Stack"
echo "========================================"

kill_service "Sync Daemon"          "$LOGS_DIR/sync_daemon.pid"    "$PROJECT_ROOT/scripts/sync_worker.py"
kill_service "Dashboard"            "$LOGS_DIR/dashboard.pid"      "$PROJECT_ROOT/dashboard3/app.py"
kill_service "Discord Bot"          "$LOGS_DIR/bot.pid"            "python.*bot\.py"
kill_service "Scrapers"             "$LOGS_DIR/scrapers.pid"       "$PROJECT_ROOT/scripts/scraper_daemon.sh"
kill_service "Monthly Views Daemon" "$LOGS_DIR/monthly_views.pid"  "$PROJECT_ROOT/scripts/view_snapshot_daemon.sh"

# Clean up legacy pidfile
rm -f "$PROJECT_ROOT/dashboard3/.dashboard3.pid"

echo ""
echo "========================================"
echo "✅ Full stack stopped"
echo "========================================"
