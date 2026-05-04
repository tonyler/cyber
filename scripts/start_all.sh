#!/bin/bash
# Start full Cybernetics stack: dashboard, sync daemon, Discord bot, scrapers.
# Assumes stop_all.sh has already been called (or services are not running).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOGS_DIR="$PROJECT_ROOT/logs"
ROOT_VENV="$PROJECT_ROOT/venv"

log_warn() { echo "⚠️  $1"; }

# Start a service, write its PID, verify it's alive.
# Usage: start_service <name> <pidfile> <pattern> <log> <cmd...>
start_service() {
    local name="$1" pidfile="$2" pattern="$3" logfile="$4"
    shift 4

    nohup "$@" >> "$logfile" 2>&1 &

    # Wait briefly then resolve to the actual process (python, not bash wrapper)
    sleep 2
    local pid
    pid="$(pgrep -f -- "$pattern" 2>/dev/null | head -n 1 || true)"

    if [ -z "$pid" ] || ! ps -p "$pid" > /dev/null 2>&1; then
        log_warn "$name failed to start — check $logfile"
        return 0  # Don't abort the whole stack for one service
    fi

    echo "$pid" > "$pidfile"
    echo "✅ $name started (PID: $pid)"
}

mkdir -p "$LOGS_DIR"

echo "========================================"
echo "Starting Full Cybernetics Stack"
echo "========================================"

# --- Sync Daemon + Dashboard (via start_cybernetics.sh) ---
if [ -f "$SCRIPT_DIR/start_cybernetics.sh" ]; then
    CYBER_DASHBOARD_DIR="$PROJECT_ROOT/dashboard3" bash "$SCRIPT_DIR/start_cybernetics.sh" || \
        log_warn "Cybernetics core failed to start; continuing with remaining services."
else
    log_warn "Missing start_cybernetics.sh; skipping core services."
fi

# --- Discord Bot ---
echo ""
echo "Starting Discord Bot..."
if [ ! -f "$PROJECT_ROOT/bot/bot.py" ]; then
    log_warn "bot/bot.py missing; skipping Discord bot."
elif [ ! -f "$PROJECT_ROOT/.env" ]; then
    log_warn ".env missing; skipping Discord bot."
else
    # Pattern matches "python* bot.py" regardless of full path (start.sh runs: python3 -u bot.py)
    start_service "Discord Bot" \
        "$LOGS_DIR/bot.pid" \
        "python.*bot\.py" \
        "$LOGS_DIR/bot.log" \
        bash "$PROJECT_ROOT/bot/start.sh"
fi

# --- Scrapers ---
echo ""
echo "Starting Scrapers (X + Reddit) every 30 minutes..."
if [ ! -f "$PROJECT_ROOT/scripts/scraper_daemon.sh" ]; then
    log_warn "scraper_daemon.sh missing; skipping scrapers."
else
    export PYTHON_BIN="${PYTHON_BIN:-$ROOT_VENV/bin/python3}"
    start_service "Scrapers" \
        "$LOGS_DIR/scrapers.pid" \
        "$PROJECT_ROOT/scripts/scraper_daemon.sh" \
        "$LOGS_DIR/scrapers.log" \
        bash "$PROJECT_ROOT/scripts/scraper_daemon.sh"
fi

# --- Monthly Views Daemon ---
echo ""
echo "Starting Monthly Views Snapshot Daemon (runs at 00:00 UTC)..."
if [ ! -f "$PROJECT_ROOT/scripts/view_snapshot_daemon.sh" ]; then
    log_warn "view_snapshot_daemon.sh missing; skipping statistics scheduler."
else
    start_service "Monthly Views Daemon" \
        "$LOGS_DIR/monthly_views.pid" \
        "$PROJECT_ROOT/scripts/view_snapshot_daemon.sh" \
        "$LOGS_DIR/monthly_views.log" \
        bash "$PROJECT_ROOT/scripts/view_snapshot_daemon.sh"
fi

echo ""
echo "========================================"
echo "✅ Full stack started"
echo "========================================"
echo "Dashboard URL: http://localhost:5002"
echo "Logs:"
echo "  Sync:     $LOGS_DIR/sync_daemon.log"
echo "  Dashboard: $LOGS_DIR/dashboard.log"
echo "  Bot:      $LOGS_DIR/bot.log"
echo "  Scrapers: $LOGS_DIR/scrapers.log"
