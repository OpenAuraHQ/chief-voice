#!/bin/zsh
# Chief control.  Usage: ./chief.sh on | off | restart | status | log | autostart on|off
# Settings: put CHIEF_* variables (see README) in ~/.chief/config.env; they are read on every start.
set -u
umask 077  # log, state and output files are private to this user
DIR="${0:A:h}"
CHIEF_HOME="${CHIEF_HOME:-$HOME/.chief}"
PY="$DIR/.venv/bin/python"
LABEL="com.openaura.chief"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p -m 700 "$CHIEF_HOME"

running() { pgrep -f "$DIR/chief.py" >/dev/null; }

start() {
  [[ -x "$PY" ]] || { echo "Chief is not installed yet: run ./install.sh"; exit 1; }
  running && { echo "Chief is already on"; return; }
  [[ -f "$CHIEF_HOME/config.env" ]] && { set -a; source "$CHIEF_HOME/config.env"; set +a; }
  # The model was downloaded at install; run offline so nothing can reach the network at runtime.
  HF_HUB_OFFLINE=1 nohup "$PY" -I "$DIR/chief.py" >> "$CHIEF_HOME/chief.out" 2>&1 &
  sleep 6
  running && { echo "Chief is on"; tail -1 "$CHIEF_HOME/chief.log" 2>/dev/null; } \
          || { echo "Chief failed to start; see $CHIEF_HOME/chief.out"; tail -5 "$CHIEF_HOME/chief.out"; exit 1; }
}

stop() { pkill -f "$DIR/chief.py" && echo "Chief is off" || echo "Chief was not running"; }

case "${1:-}" in
  on) start ;;
  off) stop ;;
  restart) stop; sleep 1; start ;;
  status) running && echo "Chief is on" || echo "Chief is off"; tail -3 "$CHIEF_HOME/chief.log" 2>/dev/null ;;
  log) tail -f "$CHIEF_HOME/chief.log" ;;
  autostart)
    case "${2:-}" in
      on)
        mkdir -p "$HOME/Library/LaunchAgents"
        cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/zsh</string><string>$DIR/chief.sh</string><string>on</string></array>
  <key>RunAtLoad</key><true/>
  <key>ProcessType</key><string>Interactive</string>
</dict></plist>
EOF
        echo "Chief will start at login ($PLIST)" ;;
      off) rm -f "$PLIST"; echo "Chief will no longer start at login" ;;
      *) echo "usage: ./chief.sh autostart on|off" ;;
    esac ;;
  *) echo "usage: ./chief.sh on | off | restart | status | log | autostart on|off" ;;
esac
