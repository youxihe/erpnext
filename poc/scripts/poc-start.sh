#!/bin/bash
# 启动 POC bench 服务（web + socketio + worker + schedule）
# 使用 pidfile 判定进程状态，避免 pgrep 自匹配误判
BENCH=/workspace/development/frappe-bench
LOG=/workspace/logs
RUN=/workspace/run
mkdir -p "$LOG" "$RUN"
cd "$BENCH" || exit 1
export FRAPPE_BIND_ADDR=0.0.0.0
# 让前端 socket.io 客户端按 socketio_port 端口连接（bench start 才会自动设置）
export DEV_SERVER=true

alive() { [ -f "$RUN/$1.pid" ] && kill -0 "$(cat "$RUN/$1.pid")" 2>/dev/null; }

start_proc() { # name logfile command...
  local name="$1" logfile="$2"; shift 2
  if alive "$name"; then
    echo "$name already running (pid $(cat "$RUN/$name.pid"))"
    return
  fi
  rm -f "$RUN/$name.pid"
  nohup "$@" > "$logfile" 2>&1 &
  echo $! > "$RUN/$name.pid"
  echo "$name started (pid $!)"
}

# 中文字体（仅影响容器内无头截图渲染，不影响 ERPNext 本身）
if [ ! -f /usr/share/fonts/truetype/cn/msyh.ttc ] && [ -f /hostshare/fonts/msyh.ttc ]; then
  sudo mkdir -p /usr/share/fonts/truetype/cn
  sudo cp /hostshare/fonts/msyh.ttc /usr/share/fonts/truetype/cn/
  sudo fc-cache -f >/dev/null 2>&1
fi

start_proc web       "$LOG/web.log"       bench serve --port 8000
start_proc socketio  "$LOG/socketio.log"  bench socketio
start_proc worker    "$LOG/worker.log"    bench worker
start_proc schedule  "$LOG/schedule.log"  bench schedule
echo "--- all started ---"
