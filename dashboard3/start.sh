#!/bin/bash
# Start Dashboard 3.0

cd "$(dirname "$0")"

PID_FILE=".dashboard3.pid"
LOG_DIR="../logs"
LOG_FILE="${LOG_DIR}/dashboard3.log"

echo "🚀 Starting Cybernetics Dashboard 3.0..."

# Check if already running
if [ -f "${PID_FILE}" ]; then
    existing_pid="$(cat "${PID_FILE}")"
    if [ -n "${existing_pid}" ] && kill -0 "${existing_pid}" 2>/dev/null; then
        echo "⚠️  Dashboard is already running! (PID: ${existing_pid})"
        echo ""
        echo "Access at: http://localhost:5002"
        echo ""
        echo "To restart: ./stop.sh && ./start.sh"
        exit 0
    fi
    rm -f "${PID_FILE}"
fi

# Start dashboard
source venv/bin/activate
mkdir -p "${LOG_DIR}"
nohup python3 app.py > "${LOG_FILE}" 2>&1 &
echo $! > "${PID_FILE}"

sleep 3

# Check if started successfully
if [ -f "${PID_FILE}" ] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    echo "✅ Dashboard 3.0 is now running!"
    echo ""
    echo "🌐 Access the dashboard:"
    echo "   http://localhost:5002"
    echo ""
    echo "📝 View logs: tail -f ${LOG_FILE}"
    echo "📊 Check status: ./status.sh"
    echo "🛑 Stop dashboard: ./stop.sh"
else
    echo "❌ Failed to start dashboard"
    echo ""
    echo "Check logs:"
    tail -10 "${LOG_FILE}"
fi
