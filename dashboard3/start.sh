#!/bin/bash
# Start Dashboard 3.0

cd "$(dirname "$0")"

PID_FILE=".dashboard3.pid"
LOG_DIR="../logs"
LOG_FILE="${LOG_DIR}/dashboard3.log"
PYTHON_BIN=""
GUNICORN_BIN=""
APP_PATH="$(pwd)/app.py"

systemd_dashboard_active() {
    command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet cyber-dashboard.service
}

find_existing_pid() {
    pgrep -f -- "${APP_PATH}" 2>/dev/null | head -n 1 || true
}

echo "🚀 Starting Cybernetics Dashboard 3.0..."

if systemd_dashboard_active; then
    echo "⚠️  cyber-dashboard.service is already managing the dashboard."
    echo ""
    echo "Access at: http://localhost:5002"
    echo ""
    echo "Use: systemctl status cyber-dashboard.service"
    exit 0
fi

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

existing_pid="$(find_existing_pid)"
if [ -n "${existing_pid}" ] && kill -0 "${existing_pid}" 2>/dev/null; then
    echo "${existing_pid}" > "${PID_FILE}"
    echo "⚠️  Dashboard is already running! (PID: ${existing_pid})"
    echo ""
    echo "Access at: http://localhost:5002"
    echo ""
    echo "To restart: ./stop.sh && ./start.sh"
    exit 0
fi

# Resolve Python interpreter and gunicorn (prefer project venv)
if [ -x "../venv/bin/python3" ]; then
    PYTHON_BIN="../venv/bin/python3"
    GUNICORN_BIN="../venv/bin/gunicorn"
elif [ -x "venv/bin/python3" ]; then
    PYTHON_BIN="venv/bin/python3"
    GUNICORN_BIN="venv/bin/gunicorn"
else
    PYTHON_BIN="$(command -v python3 || true)"
    GUNICORN_BIN="$(command -v gunicorn || true)"
fi

if [ -z "${PYTHON_BIN}" ]; then
    echo "❌ python3 not found"
    exit 1
fi

# Start dashboard — use gunicorn if available, fall back to flask dev server
mkdir -p "${LOG_DIR}"
if [ -x "${GUNICORN_BIN}" ]; then
    nohup "${GUNICORN_BIN}" \
        --workers 3 \
        --bind 0.0.0.0:5002 \
        --timeout 60 \
        --access-logfile "${LOG_DIR}/dashboard3.access.log" \
        --error-logfile "${LOG_FILE}" \
        app:app > /dev/null 2>&1 &
else
    echo "⚠️  gunicorn not found, falling back to Flask dev server"
    nohup "${PYTHON_BIN}" app.py > "${LOG_FILE}" 2>&1 &
fi
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
