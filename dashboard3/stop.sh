#!/bin/bash
# Stop Dashboard 3.0

echo "🛑 Stopping Cybernetics Dashboard 3.0..."

PID_FILE=".dashboard3.pid"

if [ ! -f "${PID_FILE}" ]; then
    echo "⚠️  Dashboard is not running"
    exit 0
fi

pid="$(cat "${PID_FILE}")"
if [ -z "${pid}" ] || ! kill -0 "${pid}" 2>/dev/null; then
    rm -f "${PID_FILE}"
    echo "⚠️  Dashboard is not running"
    exit 0
fi

# Try graceful shutdown first
kill "${pid}"
sleep 2

# Check if stopped
if ! kill -0 "${pid}" 2>/dev/null; then
    rm -f "${PID_FILE}"
    echo "✅ Dashboard stopped successfully"
else
    echo "⚠️  Forcing shutdown..."
    kill -9 "${pid}"
    sleep 1

    if ! kill -0 "${pid}" 2>/dev/null; then
        rm -f "${PID_FILE}"
        echo "✅ Dashboard force-stopped"
    else
        echo "❌ Failed to stop dashboard"
        echo "PID ${pid} is still running."
    fi
fi
