#!/bin/bash
# Stop Dashboard 2.0

echo "🛑 Stopping Cybernetics Dashboard 2.0..."

if ! pgrep -f "python3 app.py" > /dev/null; then
    echo "⚠️  Dashboard is not running"
    exit 0
fi

# Try graceful shutdown first
pkill -f "python3 app.py"
sleep 2

# Check if stopped
if ! pgrep -f "python3 app.py" > /dev/null; then
    echo "✅ Dashboard stopped successfully"
else
    echo "⚠️  Forcing shutdown..."
    pkill -9 -f "python3 app.py"
    sleep 1

    if ! pgrep -f "python3 app.py" > /dev/null; then
        echo "✅ Dashboard force-stopped"
    else
        echo "❌ Failed to stop dashboard"
        echo "Running processes:"
        ps aux | grep "python3 app.py" | grep -v grep
    fi
fi
