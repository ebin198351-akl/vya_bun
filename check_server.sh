#!/usr/bin/env bash

# 服务器诊断脚本 - 检查服务器状态和常见问题
# Usage: ./check_server.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
PID_FILE="$SCRIPT_DIR/server.pid"
LOG_FILE="$SCRIPT_DIR/server.log"
PORT="${PORT:-8000}"

echo "=========================================="
echo "Vya's Kitchen Server Diagnostic Check"
echo "=========================================="
echo ""

# 1. 检查 Python 是否可用
echo "1. Checking Python..."
if command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_VERSION=$($PYTHON_BIN --version 2>&1)
    echo "   ✓ Python found: $PYTHON_VERSION"
else
    echo "   ✗ Python not found: $PYTHON_BIN"
    echo "   Try: which python3"
    exit 1
fi
echo ""

# 2. 检查依赖
echo "2. Checking dependencies..."
if [ -f "requirements.txt" ]; then
    MISSING_DEPS=0
    while IFS= read -r dep; do
        dep_name=$(echo "$dep" | cut -d'=' -f1 | cut -d'>' -f1 | cut -d'<' -f1 | tr -d ' ')
        if [ -n "$dep_name" ]; then
            if $PYTHON_BIN -c "import $dep_name" 2>/dev/null; then
                echo "   ✓ $dep_name"
            else
                echo "   ✗ $dep_name (missing)"
                MISSING_DEPS=1
            fi
        fi
    done < requirements.txt
    if [ $MISSING_DEPS -eq 1 ]; then
        echo "   Run: $PYTHON_BIN -m pip install -r requirements.txt"
    fi
else
    echo "   ⚠ requirements.txt not found"
fi
echo ""

# 3. 检查服务器文件
echo "3. Checking server files..."
if [ -f "server.py" ]; then
    echo "   ✓ server.py found"
    # 检查语法
    if $PYTHON_BIN -m py_compile server.py 2>/dev/null; then
        echo "   ✓ server.py syntax OK"
    else
        echo "   ✗ server.py has syntax errors!"
        $PYTHON_BIN -m py_compile server.py
    fi
else
    echo "   ✗ server.py not found!"
    exit 1
fi

if [ -f "send_email.py" ]; then
    echo "   ✓ send_email.py found"
else
    echo "   ⚠ send_email.py not found"
fi
echo ""

# 4. 检查进程状态
echo "4. Checking server process..."
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$PID" ]; then
        if kill -0 "$PID" 2>/dev/null; then
            echo "   ✓ Server process running (PID: $PID)"
            # 检查进程详情
            if command -v ps >/dev/null 2>&1; then
                ps -p "$PID" -o pid,cmd,etime 2>/dev/null | tail -n +2
            fi
        else
            echo "   ✗ PID file exists but process is not running (PID: $PID)"
            echo "   Remove stale PID file: rm $PID_FILE"
        fi
    else
        echo "   ⚠ PID file is empty"
    fi
else
    echo "   ⚠ No PID file found (server may not be running)"
    # 尝试查找 server.py 进程
    if pgrep -f "server.py" >/dev/null 2>&1; then
        echo "   Found server.py processes:"
        pgrep -f "server.py" | xargs ps -p 2>/dev/null || true
    fi
fi
echo ""

# 5. 检查端口
echo "5. Checking port $PORT..."
if command -v netstat >/dev/null 2>&1; then
    if netstat -tuln 2>/dev/null | grep -q ":$PORT "; then
        echo "   ✓ Port $PORT is in use"
        netstat -tuln 2>/dev/null | grep ":$PORT " || true
    else
        echo "   ✗ Port $PORT is not in use (server may not be listening)"
    fi
elif command -v ss >/dev/null 2>&1; then
    if ss -tuln 2>/dev/null | grep -q ":$PORT "; then
        echo "   ✓ Port $PORT is in use"
        ss -tuln 2>/dev/null | grep ":$PORT " || true
    else
        echo "   ✗ Port $PORT is not in use (server may not be listening)"
    fi
else
    echo "   ⚠ Cannot check port (netstat/ss not available)"
fi
echo ""

# 6. 检查日志
echo "6. Checking server logs..."
if [ -f "$LOG_FILE" ]; then
    LOG_SIZE=$(wc -l < "$LOG_FILE" 2>/dev/null || echo "0")
    echo "   Log file: $LOG_FILE ($LOG_SIZE lines)"
    echo "   Last 10 lines:"
    tail -n 10 "$LOG_FILE" 2>/dev/null | sed 's/^/   /'
    
    # 检查错误
    if grep -i "error\|exception\|traceback\|failed" "$LOG_FILE" >/dev/null 2>&1; then
        echo ""
        echo "   ⚠ ERRORS FOUND in log:"
        grep -i "error\|exception\|traceback\|failed" "$LOG_FILE" | tail -n 5 | sed 's/^/   /'
    fi
else
    echo "   ⚠ Log file not found: $LOG_FILE"
fi
echo ""

# 7. 测试健康检查端点
echo "7. Testing health endpoint..."
if command -v curl >/dev/null 2>&1; then
    if curl -s -f "http://localhost:$PORT/health" >/dev/null 2>&1; then
        echo "   ✓ Health check passed"
        curl -s "http://localhost:$PORT/health" | head -n 1
    else
        echo "   ✗ Health check failed (server may not be responding)"
    fi
elif command -v wget >/dev/null 2>&1; then
    if wget -q -O- "http://localhost:$PORT/health" >/dev/null 2>&1; then
        echo "   ✓ Health check passed"
    else
        echo "   ✗ Health check failed (server may not be responding)"
    fi
else
    echo "   ⚠ Cannot test (curl/wget not available)"
fi
echo ""

# 8. 建议
echo "=========================================="
echo "Recommendations:"
echo "=========================================="

if [ ! -f "$PID_FILE" ] || ! kill -0 "$(cat "$PID_FILE" 2>/dev/null)" 2>/dev/null; then
    echo "• Server is not running. Start it with:"
    echo "  ./start.sh start"
    echo ""
fi

if [ -f "$LOG_FILE" ] && grep -qi "address already in use\|port.*in use" "$LOG_FILE" 2>/dev/null; then
    echo "• Port conflict detected. Try:"
    echo "  ./start.sh stop"
    echo "  # Wait a few seconds"
    echo "  ./start.sh start"
    echo ""
fi

if [ -f "$LOG_FILE" ] && grep -qi "permission denied\|cannot bind" "$LOG_FILE" 2>/dev/null; then
    echo "• Permission issue detected. Try:"
    echo "  sudo ./start.sh start"
    echo "  # Or use a port > 1024 (set PORT environment variable)"
    echo ""
fi

echo "• View full logs:"
echo "  tail -f $LOG_FILE"
echo ""
echo "• Check if server is accessible:"
echo "  curl http://localhost:$PORT/health"
echo ""
