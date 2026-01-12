#!/bin/bash
# Start Dashboard 2.0

cd "$(dirname "$0")"

echo "🚀 Starting Cybernetics Dashboard 2.0..."

# Check if already running
if pgrep -f "python3 app.py" > /dev/null; then
    echo "⚠️  Dashboard is already running!"
    echo ""
    ps aux | grep "python3 app.py" | grep -v grep
    echo ""
    echo "Access at: http://37.27.15.9:5003"
    echo ""
    echo "To restart: ./stop.sh && ./start.sh"
    exit 0
fi

# Start dashboard
source venv/bin/activate
nohup python3 app.py > /tmp/dashboard2.log 2>&1 &

sleep 3

# Check if started successfully
if pgrep -f "python3 app.py" > /dev/null; then
    echo "✅ Dashboard 2.0 is now running!"
    echo ""
    echo "🌐 Access the dashboard:"
    echo "   http://37.27.15.9:5003"
    echo ""
    echo "📝 View logs: tail -f /tmp/dashboard2.log"
    echo "📊 Check status: ./status.sh"
    echo "🛑 Stop dashboard: ./stop.sh"
else
    echo "❌ Failed to start dashboard"
    echo ""
    echo "Check logs:"
    tail -10 /tmp/dashboard2.log
fi
