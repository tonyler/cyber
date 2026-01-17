#!/bin/bash
# Start full Cybernetics stack: dashboard, sync daemon, Discord bot, scrapers.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOGS_DIR="$PROJECT_ROOT/logs"
ROOT_VENV="$PROJECT_ROOT/venv"

log_warn() {
    echo "⚠️  $1"
}

mkdir -p "$LOGS_DIR"

echo "========================================"
echo "Starting Full Cybernetics Stack"
echo "========================================"

# Start dashboard + sync daemon (system script)
if [ -f "$SCRIPT_DIR/start_cybernetics.sh" ]; then
    CYBER_DASHBOARD_DIR="$PROJECT_ROOT/dashboard3" bash "$SCRIPT_DIR/start_cybernetics.sh" || \
        log_warn "Cybernetics core failed to start; continuing with remaining services."
else
    log_warn "Missing start_cybernetics.sh; skipping core services."
fi

echo ""
echo "Starting Discord Bot..."
if [ -f "$LOGS_DIR/bot.pid" ]; then
    BOT_PID="$(cat "$LOGS_DIR/bot.pid")"
    if ps -p "$BOT_PID" > /dev/null 2>&1; then
        echo "✅ Bot already running (PID: $BOT_PID)"
    else
        rm -f "$LOGS_DIR/bot.pid"
    fi
fi

if [ ! -f "$LOGS_DIR/bot.pid" ]; then
    if [ ! -f "$PROJECT_ROOT/bot/start.sh" ] || [ ! -f "$PROJECT_ROOT/bot/bot.py" ]; then
        log_warn "Bot entrypoint missing; skipping Discord bot."
    elif [ ! -f "$PROJECT_ROOT/.env" ]; then
        log_warn "Project .env missing at $PROJECT_ROOT/.env; skipping Discord bot."
    else
        if [ ! -f "$PROJECT_ROOT/bot/requirements.txt" ]; then
            log_warn "Bot requirements.txt missing; attempting to start with existing environment."
        fi
        nohup bash "$PROJECT_ROOT/bot/start.sh" > "$LOGS_DIR/bot.log" 2>&1 &
        BOT_PID=$!
        echo "$BOT_PID" > "$LOGS_DIR/bot.pid"
        echo "✅ Bot started (PID: $BOT_PID)"
        echo "Logs: $LOGS_DIR/bot.log"
    fi
fi

echo ""
echo "Starting Scrapers (X + Reddit) every 30 minutes..."
if [ -f "$LOGS_DIR/scrapers.pid" ]; then
    SCRAPERS_PID="$(cat "$LOGS_DIR/scrapers.pid")"
    if ps -p "$SCRAPERS_PID" > /dev/null 2>&1; then
        echo "✅ Scrapers already running (PID: $SCRAPERS_PID)"
    else
        rm -f "$LOGS_DIR/scrapers.pid"
    fi
fi

if [ ! -f "$LOGS_DIR/scrapers.pid" ]; then
    if [ ! -f "$PROJECT_ROOT/scripts/scraper_daemon.sh" ]; then
        log_warn "Scraper daemon script missing; skipping scrapers."
    else
        export PYTHON_BIN="${PYTHON_BIN:-$ROOT_VENV/bin/python3}"
        nohup bash "$PROJECT_ROOT/scripts/scraper_daemon.sh" > "$LOGS_DIR/scrapers.log" 2>&1 &
        SCRAPERS_PID=$!
        echo "$SCRAPERS_PID" > "$LOGS_DIR/scrapers.pid"
        echo "✅ Scraper daemon started (PID: $SCRAPERS_PID)"
        echo "Logs: $LOGS_DIR/scrapers.log"
    fi
fi

echo ""
echo "Starting Monthly Views Snapshot Daemon (runs at 00:00 UTC)..."
if [ -f "$LOGS_DIR/monthly_views.pid" ]; then
    MV_PID="$(cat "$LOGS_DIR/monthly_views.pid")"
    if ps -p "$MV_PID" > /dev/null 2>&1; then
        echo "✅ Monthly views daemon already running (PID: $MV_PID)"
    else
        rm -f "$LOGS_DIR/monthly_views.pid"
    fi
fi

if [ ! -f "$LOGS_DIR/monthly_views.pid" ]; then
    if [ ! -f "$PROJECT_ROOT/scripts/view_snapshot_daemon.sh" ]; then
        log_warn "Monthly views daemon missing; skipping statistics scheduler."
    else
        nohup bash "$PROJECT_ROOT/scripts/view_snapshot_daemon.sh" > "$LOGS_DIR/monthly_views.log" 2>&1 &
        MV_PID=$!
        echo "$MV_PID" > "$LOGS_DIR/monthly_views.pid"
        echo "✅ Monthly views daemon started (PID: $MV_PID)"
        echo "Logs: $LOGS_DIR/monthly_views.log"
    fi
fi

echo ""
echo "========================================"
echo "✅ Full stack started"
echo "========================================"
echo "Dashboard URL: http://localhost:5002"
echo "Logs:"
echo "  Sync: $LOGS_DIR/sync_daemon.log"
echo "  Dashboard: $LOGS_DIR/dashboard.log"
echo "  Bot: $LOGS_DIR/bot.log"
echo "  Scrapers: $LOGS_DIR/scrapers.log"
