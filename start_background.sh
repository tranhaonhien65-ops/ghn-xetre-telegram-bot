#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Force kill any existing python bot or socket listeners
pkill -9 -f "python3.*bot.py" 2>/dev/null
lsof -ti :8989 | xargs kill -9 2>/dev/null
sleep 1

# Start freshly
nohup python3 -u bot.py > bot.log 2>&1 &
echo "✅ Bot đã khởi động lại hoàn toàn mới! PID: $!"
echo "📄 Log file: $DIR/bot.log"
