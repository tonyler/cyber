#!/bin/bash
# cyber.sh — start / stop / status for the full Cyber stack
# Usage: ./cyber.sh [start|stop|status]
#
# Services managed:
#   1. Hedera Dashboard   (hederadashboard/app.py  → gunicorn :5003)
#   2. Sync Daemon        (scripts/sync_worker.py)
#   3. Discord Bot        (bot/bot.py)
#   4. Scraper Daemon     (scripts/scraper_daemon.sh)
#   5. Monthly Views      (scripts/view_snapshot_daemon.sh)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS="$ROOT/logs"
VENV="$ROOT/venv"
PYTHON="$VENV/bin/python3"

mkdir -p "$LOGS"

# ── helpers ──────────────────────────────────────────────────────────────────

_pid_running() { [ -n "$1" ] && ps -p "$1" > /dev/null 2>&1; }

_find_pid() { pgrep -f -- "$1" 2>/dev/null | head -n 1 || true; }

_start() {
    local name="$1" pidfile="$2" pattern="$3" logfile="$4"; shift 4

    # already running?
    if [ -f "$pidfile" ]; then
        local p; p="$(cat "$pidfile" 2>/dev/null || true)"
        if _pid_running "$p"; then
            echo "  [skip] $name already running (PID $p)"; return
        fi
        rm -f "$pidfile"
    fi
    local p; p="$(_find_pid "$pattern")"
    if _pid_running "$p"; then
        echo "$p" > "$pidfile"
        echo "  [skip] $name already running (PID $p)"; return
    fi

    nohup "$@" >> "$logfile" 2>&1 &
    sleep 2
    p="$(_find_pid "$pattern")"
    if _pid_running "$p"; then
        echo "$p" > "$pidfile"
        echo "  ✅ $name started (PID $p)"
    else
        echo "  ⚠️  $name failed to start — check $logfile"
    fi
}

_stop() {
    local name="$1" pidfile="$2" pattern="$3"
    local killed=0

    if [ -f "$pidfile" ]; then
        local p; p="$(cat "$pidfile" 2>/dev/null || true)"
        if _pid_running "$p"; then kill "$p" 2>/dev/null || true; killed=1; fi
        rm -f "$pidfile"
    fi

    local pids; pids="$(_find_pid "$pattern")"
    for p in $pids; do
        if _pid_running "$p"; then kill "$p" 2>/dev/null || true; killed=1; fi
    done

    [ "$killed" -eq 0 ] && { echo "  [skip] $name not running"; return; }

    # wait up to 5 s then force-kill
    local i=0
    while [ "$i" -lt 5 ]; do
        pids="$(_find_pid "$pattern")"
        [ -z "$pids" ] && break
        sleep 1; i=$((i+1))
    done
    pids="$(_find_pid "$pattern")"
    for p in $pids; do kill -9 "$p" 2>/dev/null || true; done

    echo "  ✅ $name stopped"
}

_status() {
    local name="$1" pidfile="$2" pattern="$3" url="${4:-}"
    local p=""

    if [ -f "$pidfile" ]; then
        p="$(cat "$pidfile" 2>/dev/null || true)"
        _pid_running "$p" || { rm -f "$pidfile"; p=""; }
    fi
    [ -z "$p" ] && p="$(_find_pid "$pattern")"
    _pid_running "$p" || p=""

    if [ -n "$p" ]; then
        local info="PID $p"
        [ -n "$url" ] && info="$info  →  $url"
        echo "  ✅ $name  ($info)"
    else
        echo "  ❌ $name  (not running)"
    fi
}

# ── actions ───────────────────────────────────────────────────────────────────

cmd_start() {
    echo "========================================"
    echo " Starting Cyber stack"
    echo "========================================"

    # 1. Hedera Dashboard (gunicorn)
    echo ""
    echo "Dashboard (hederadashboard)..."
    _start "Dashboard" \
        "$LOGS/dashboard.pid" \
        "cyber/venv.*gunicorn.*5003" \
        "$LOGS/dashboard.log" \
        "$VENV/bin/gunicorn" --workers 3 --bind 0.0.0.0:5003 --timeout 60 \
            --chdir "$ROOT/hederadashboard" app:app

    # 2. Sync daemon
    echo ""
    echo "Sync daemon..."
    if [ -f "$ROOT/scripts/sync_worker.py" ]; then
        _start "Sync Daemon" \
            "$LOGS/sync_daemon.pid" \
            "sync_worker\.py" \
            "$LOGS/sync_daemon.log" \
            "$PYTHON" "$ROOT/scripts/sync_worker.py"
    else
        echo "  [skip] sync_worker.py not found"
    fi

    # 3. Discord bot
    echo ""
    echo "Discord bot..."
    if [ ! -f "$ROOT/bot/bot.py" ]; then
        echo "  [skip] bot/bot.py not found"
    elif [ ! -f "$ROOT/.env" ]; then
        echo "  [skip] .env not found"
    else
        _start "Discord Bot" \
            "$LOGS/bot.pid" \
            "cyber/bot/bot\.py" \
            "$LOGS/bot.log" \
            "$PYTHON" -u "$ROOT/bot/bot.py"
    fi

    # 4. Scraper daemon
    echo ""
    echo "Scraper daemon..."
    if [ -f "$ROOT/scripts/scraper_daemon.sh" ]; then
        _start "Scrapers" \
            "$LOGS/scrapers.pid" \
            "$ROOT/scripts/scraper_daemon.sh" \
            "$LOGS/scrapers.log" \
            bash "$ROOT/scripts/scraper_daemon.sh"
    else
        echo "  [skip] scraper_daemon.sh not found"
    fi

    # 5. Monthly views daemon
    echo ""
    echo "Monthly views daemon..."
    if [ -f "$ROOT/scripts/view_snapshot_daemon.sh" ]; then
        _start "Monthly Views" \
            "$LOGS/monthly_views.pid" \
            "$ROOT/scripts/view_snapshot_daemon.sh" \
            "$LOGS/monthly_views.log" \
            bash "$ROOT/scripts/view_snapshot_daemon.sh"
    else
        echo "  [skip] view_snapshot_daemon.sh not found"
    fi

    echo ""
    echo "========================================"
    echo " Done.  Dashboard → http://localhost:5003"
    echo "========================================"
}

cmd_stop() {
    echo "========================================"
    echo " Stopping Cyber stack"
    echo "========================================"
    echo ""
    _stop "Dashboard"      "$LOGS/dashboard.pid"      "cyber/venv.*gunicorn.*5003"
    _stop "Sync Daemon"    "$LOGS/sync_daemon.pid"    "sync_worker\.py"
    _stop "Discord Bot"    "$LOGS/bot.pid"            "cyber/bot/bot\.py"
    _stop "Scrapers"       "$LOGS/scrapers.pid"        "$ROOT/scripts/scraper_daemon.sh"
    _stop "Monthly Views"  "$LOGS/monthly_views.pid"   "$ROOT/scripts/view_snapshot_daemon.sh"
    # tidy up hederadashboard legacy pidfile
    rm -f "$ROOT/hederadashboard/.hederadashboard.pid"
    echo ""
    echo "========================================"
    echo " Stopped."
    echo "========================================"
}

cmd_status() {
    echo "========================================"
    echo " Cyber stack status"
    echo "========================================"
    echo ""
    _status "Dashboard"      "$LOGS/dashboard.pid"      "cyber/venv.*gunicorn.*5003"  "http://localhost:5003"
    _status "Sync Daemon"    "$LOGS/sync_daemon.pid"    "sync_worker\.py"
    _status "Discord Bot"    "$LOGS/bot.pid"            "cyber/bot/bot\.py"
    _status "Scrapers"       "$LOGS/scrapers.pid"       "$ROOT/scripts/scraper_daemon.sh"
    _status "Monthly Views"  "$LOGS/monthly_views.pid"  "$ROOT/scripts/view_snapshot_daemon.sh"
    echo ""
    echo "========================================"
}

# ── entry point ───────────────────────────────────────────────────────────────

case "${1:-status}" in
    start)  cmd_start ;;
    stop)   cmd_stop  ;;
    status) cmd_status ;;
    restart) cmd_stop; echo ""; cmd_start ;;
    *) echo "Usage: $0 [start|stop|restart|status]"; exit 1 ;;
esac
