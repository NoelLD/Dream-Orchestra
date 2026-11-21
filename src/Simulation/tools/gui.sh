#!/usr/bin/env bash
# Start a virtual display with a browser view (noVNC on :6080), then run the given command in it.
# Usage (host): docker compose up -d simulation-gui   -> open http://localhost:6080/vnc.html?autoconnect=1&resize=scale
set -euo pipefail
export DISPLAY=:1
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1   # stale after a container restart
Xvfb :1 -screen 0 1280x800x24 >/tmp/xvfb.log 2>&1 &
for _ in $(seq 50); do [ -e /tmp/.X11-unix/X1 ] && break; sleep 0.1; done
fluxbox >/tmp/fluxbox.log 2>&1 &
x11vnc -display :1 -forever -shared -nopw -quiet >/tmp/x11vnc.log 2>&1 &
websockify --web /usr/share/novnc 6080 localhost:5900 >/tmp/novnc.log 2>&1 &
echo "GUI ready: http://localhost:6080/vnc.html?autoconnect=1&resize=scale"
exec "$@"
