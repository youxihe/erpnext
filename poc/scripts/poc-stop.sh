#!/bin/bash
# 停止 POC bench 进程（容器与数据不受影响）
RUN=/workspace/run
mkdir -p "$RUN"

for name in web socketio worker schedule; do
  if [ -f "$RUN/$name.pid" ]; then
    pid=$(cat "$RUN/$name.pid")
    # 先杀子进程（werkzeug reloader 会派生子进程），再杀主进程
    pkill -P "$pid" 2>/dev/null
    kill "$pid" 2>/dev/null
    rm -f "$RUN/$name.pid"
  fi
done

# 兜底：按真实进程名清理（真实进程是 python -m frappe.utils.bench_helper frappe <子命令>）
pkill -f "bench_helper frappe serve" 2>/dev/null
pkill -f "bench_helper frappe worker" 2>/dev/null
pkill -f "bench_helper frappe schedule" 2>/dev/null
pkill -f "apps/frappe/socketio" 2>/dev/null
sleep 2
echo "--- bench processes stopped ---"
