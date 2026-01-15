#!/bin/bash
# Stop full Cybernetics stack: dashboard, sync daemon, Discord bot, scrapers.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOGS_DIR="$PROJECT_ROOT/logs"

stop_by_pidfile() {
    local name="$1"
    local pidfile="$2"

    if [ ! -f "$pidfile" ]; then
        echo "⚠️  $name PID file not found"
        return
    fi

    local pid
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if [ -z "$pid" ]; then
        echo "⚠️  $name PID file empty"
        rm -f "$pidfile"
        return
    fi

    if ps -p "$pid" > /dev/null 2>&1; then
        echo "Stopping $name (PID: $pid)..."
        kill "$pid" || true
        for _ in {1..10}; do
            if ps -p "$pid" > /dev/null 2>&1; then
                sleep 1
            else
                break
            fi
        done
        if ps -p "$pid" > /dev/null 2>&1; then
            echo "⚠️  $name did not stop, sending SIGKILL"
            kill -9 "$pid" || true
        fi
        echo "✅ $name stopped"
    else
        echo "⚠️  $name not running (stale PID file)"
    fi

    rm -f "$pidfile"
}

stop_stray_bot_processes() {
    local found=0
    local target_dir="$PROJECT_ROOT/bot"
    local target_cmd="$PROJECT_ROOT/bot/bot.py"

    for pid in $(pgrep -f "python.*bot.py" 2>/dev/null || true); do
        local cwd cmd
        cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
        cmd="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"

        if [ "$cwd" = "$target_dir" ] || [[ "$cmd" == *"$target_cmd"* ]]; then
            found=1
            echo "Stopping stray Discord Bot process (PID: $pid)..."
            kill "$pid" || true
            for _ in {1..10}; do
                if ps -p "$pid" > /dev/null 2>&1; then
                    sleep 1
                else
                    break
                fi
            done
            if ps -p "$pid" > /dev/null 2>&1; then
                echo "⚠️  Stray Discord Bot process did not stop, sending SIGKILL"
                kill -9 "$pid" || true
            fi
        fi
    done

    if [ "$found" -eq 0 ]; then
        echo "✅ No stray Discord Bot processes found"
    fi
}

echo "========================================"
echo "Stopping Full Cybernetics Stack"
echo "========================================"

stop_by_pidfile "Sync Daemon" "$LOGS_DIR/sync_daemon.pid"
stop_by_pidfile "Dashboard" "$LOGS_DIR/dashboard.pid"
stop_by_pidfile "Discord Bot" "$LOGS_DIR/bot.pid"
stop_stray_bot_processes
stop_by_pidfile "Scrapers" "$LOGS_DIR/scrapers.pid"
stop_by_pidfile "Monthly Views Daemon" "$LOGS_DIR/monthly_views.pid"

echo ""
echo "========================================"
echo "✅ Full stack stopped"
echo "========================================"
