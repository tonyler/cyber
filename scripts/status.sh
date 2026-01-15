#!/bin/bash
# Check status of all Cybernetics services

echo "========================================"
echo "Cybernetics System Status"
echo "========================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOGS_DIR="$PROJECT_ROOT/logs"

# Check Bot
echo "Discord Bot:"
if [ -f "$LOGS_DIR/bot.pid" ]; then
    BOT_PID=$(cat "$LOGS_DIR/bot.pid")
    if ps -p "$BOT_PID" > /dev/null 2>&1; then
        echo "  ✅ Running (PID: $BOT_PID)"
        echo "  Log: $LOGS_DIR/bot.log"
    else
        echo "  ❌ Not running (stale PID file)"
    fi
else
    echo "  ❌ Not running (no PID file)"
fi

echo ""

# Check Scrapers
echo "Scrapers Daemon:"
if [ -f "$LOGS_DIR/scrapers.pid" ]; then
    SCRAPERS_PID=$(cat "$LOGS_DIR/scrapers.pid")
    if ps -p "$SCRAPERS_PID" > /dev/null 2>&1; then
        echo "  ✅ Running (PID: $SCRAPERS_PID)"
        echo "  Log: $LOGS_DIR/scrapers.log"
    else
        echo "  ❌ Not running (stale PID file)"
    fi
else
    echo "  ❌ Not running (no PID file)"
fi

echo ""

echo "Dashboard:"
if [ -f "$LOGS_DIR/dashboard.pid" ]; then
    DASH_PID=$(cat "$LOGS_DIR/dashboard.pid")
    if ps -p "$DASH_PID" > /dev/null 2>&1; then
        echo "  ✅ Running (PID: $DASH_PID)"
        echo "  URL: http://localhost:5004"
        echo "  Log: $LOGS_DIR/dashboard.log"
    else
        echo "  ❌ Not running (stale PID file)"
    fi
else
    echo "  ⚠️  Not configured"
fi

echo ""

# Check Sync Daemon
echo "Sync Daemon:"
if [ -f "$LOGS_DIR/sync_daemon.pid" ]; then
    SYNC_PID=$(cat "$LOGS_DIR/sync_daemon.pid")
    if ps -p "$SYNC_PID" > /dev/null 2>&1; then
        echo "  ✅ Running (PID: $SYNC_PID)"
        echo "  Log: $LOGS_DIR/sync_daemon.log"
    else
        echo "  ❌ Not running (stale PID file)"
    fi
else
    echo "  ⚠️  Not configured"
fi

echo ""
# Check Monthly Views Daemon
echo "Monthly Views Daemon:"
if [ -f "$LOGS_DIR/monthly_views.pid" ]; then
    MV_PID=$(cat "$LOGS_DIR/monthly_views.pid")
    if ps -p "$MV_PID" > /dev/null 2>&1; then
        echo "  ✅ Running (PID: $MV_PID)"
        echo "  Log: $LOGS_DIR/monthly_views.log"
    else
        echo "  ❌ Not running (stale PID file)"
    fi
else
    echo "  ⚠️  Not configured"
fi

echo ""
echo "========================================"
