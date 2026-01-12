#!/bin/bash
# Check dashboard status

echo "🔍 Checking Dashboard 2.0 Status..."
echo ""

if pgrep -f "python3 app.py" > /dev/null; then
    echo "✅ Dashboard is RUNNING"
    echo ""
    echo "📊 Process Info:"
    ps aux | grep "python3 app.py" | grep -v grep | awk '{print "   PID: " $2 "  CPU: " $3 "%  MEM: " $4 "%"}'
    echo ""
    echo "🌐 Access URL:"
    echo "   http://37.27.15.9:5003"
    echo ""
    echo "📝 Recent logs:"
    tail -5 /tmp/dashboard2.log | sed 's/^/   /'
else
    echo "❌ Dashboard is NOT running"
    echo ""
    echo "Start it with: ./start.sh"
fi
