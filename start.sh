#!/usr/bin/env bash

# 启动 / 停止 Vya's Kitchen 的简单脚本（Linux）
# 直接使用当前目录下的 server.py / send_email.py，不再使用 dist 或 build。
# Usage:
#   ./start.sh start    # 后台启动
#   ./start.sh stop     # 停止后台进程

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
PID_FILE="$SCRIPT_DIR/server.pid"

start_server() {
  echo
  echo "=============================="
  echo " Starting server in background..."
  echo "=============================="

  # 检查是否已经在运行
  if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
      echo "Server is already running with PID: $OLD_PID"
      echo "Use './start.sh stop' to stop it first."
      exit 1
    else
      echo "Removing stale PID file..."
      rm -f "$PID_FILE"
    fi
  fi

  # 可选：安装依赖（如果环境已安装可注释掉）
  if [ -f "requirements.txt" ]; then
    echo "Installing Python dependencies (if not already installed)..."
    $PYTHON_BIN -m pip install -r requirements.txt --quiet
  fi

  # 清空旧的日志文件
  LOG_FILE="$SCRIPT_DIR/server.log"
  > "$LOG_FILE"

  echo "Running server.py in background from $SCRIPT_DIR..."
  # 尝试使用 sudo（如果可用），否则直接运行
  # 注意：在 AWS 环境中，通常不需要 sudo，因为应用通常运行在非特权端口
  if command -v sudo >/dev/null 2>&1 && [ "$EUID" -ne 0 ]; then
    nohup sudo -E $PYTHON_BIN server.py >> "$LOG_FILE" 2>&1 &
  else
    nohup $PYTHON_BIN server.py >> "$LOG_FILE" 2>&1 &
  fi
  PID=$!
  echo $PID > "$PID_FILE"
  echo "Server process started. PID: $PID"
  echo "Logs: $LOG_FILE"
  
  # 等待几秒，检查服务器是否成功启动
  echo "Waiting for server to start..."
  sleep 3
  
  # 检查进程是否还在运行
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "ERROR: Server process died immediately after starting!"
    echo "Check the log file for errors:"
    echo "  tail -n 50 $LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
  fi
  
  # 检查日志中是否有明显的错误
  if [ -f "$LOG_FILE" ] && grep -i "error\|exception\|traceback\|failed" "$LOG_FILE" >/dev/null 2>&1; then
    echo "WARNING: Errors detected in log file. Check:"
    echo "  tail -n 50 $LOG_FILE"
  fi
  
  # 尝试检查端口是否在监听（如果 netstat 或 ss 可用）
  PORT="${PORT:-8000}"
  if command -v netstat >/dev/null 2>&1; then
    if netstat -tuln 2>/dev/null | grep -q ":$PORT "; then
      echo "Server appears to be listening on port $PORT"
    fi
  elif command -v ss >/dev/null 2>&1; then
    if ss -tuln 2>/dev/null | grep -q ":$PORT "; then
      echo "Server appears to be listening on port $PORT"
    fi
  fi
  
  echo "Server startup complete. Use './start.sh stop' to stop it."
}

stop_server() {
  echo "Stopping server..."
  
  if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
      echo "Stopping server PID: $PID"
      kill "$PID" || true
      # 等待进程结束
      sleep 2
      if kill -0 "$PID" 2>/dev/null; then
        echo "Process still running, forcing kill..."
        kill -9 "$PID" 2>/dev/null || true
      fi
      echo "Server stopped."
    else
      echo "No running server found for PID in $PID_FILE"
    fi
    rm -f "$PID_FILE"
  else
    echo "PID file not found, trying to kill by name..."
    if pkill -f "server.py" 2>/dev/null; then
      echo "Server process killed."
    else
      echo "No matching server.py process found"
    fi
  fi
  
  # 额外清理：确保没有残留的 Python server 进程
  sleep 1
  if pgrep -f "server.py" >/dev/null 2>&1; then
    echo "Warning: Some server.py processes may still be running"
    pgrep -f "server.py" | xargs kill -9 2>/dev/null || true
  fi
}

case "$1" in
  start|"")
    start_server
    ;;
  stop)
    stop_server
    ;;
  *)
    echo "Usage: $0 [start|stop]"
    exit 1
    ;;
esac



