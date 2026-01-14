#!/bin/bash
# Check dashboard status

echo "🔍 Checking Dashboard 3.0 Status..."
echo ""

PID_FILE=".dashboard3.pid"
LOG_DIR="../logs"
LOG_FILE="${LOG_DIR}/dashboard3.log"

if [ -f "${PID_FILE}" ] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    echo "✅ Dashboard is RUNNING"
    echo ""
    echo "📊 Process Info:"
    pid="$(cat "${PID_FILE}")"
    ps -p "${pid}" -o pid=,pcpu=,pmem= | awk '{print "   PID: " $1 "  CPU: " $2 "%  MEM: " $3 "%"}'
    echo ""
    echo "🌐 Access URL:"
    echo "   http://localhost:5004"
    echo ""
    echo "📝 Recent logs:"
    if [ -f "${LOG_FILE}" ]; then
        tail -5 "${LOG_FILE}" | sed 's/^/   /'
    else
        echo "   (no log file yet)"
    fi
else
    echo "❌ Dashboard is NOT running"
    echo ""
    echo "Start it with: ./start.sh"
fi
