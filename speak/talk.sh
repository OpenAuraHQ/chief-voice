#!/bin/bash
# /talk control: talk.sh [on|off|stop|status|quiet]   (no argument = toggle)
#   quiet = the next reply is silent, then voice carries on
DIR="$HOME/.claude/chief-speak"
mkdir -p -m 700 "$DIR"
stop_audio() { [ -f "$DIR/play.pid" ] && kill "$(cat "$DIR/play.pid")" 2>/dev/null; rm -f "$DIR/play.pid"; }

case "${1:-toggle}" in
  on)     touch "$DIR/on"; echo "voice on" ;;
  off)    rm -f "$DIR/on"; stop_audio; echo "voice off" ;;
  stop)   stop_audio; echo "stopped" ;;
  quiet)  touch "$DIR/skip_once"; echo "next reply silent" ;;
  status) [ -f "$DIR/on" ] && echo "voice on" || echo "voice off" ;;
  toggle) if [ -f "$DIR/on" ]; then rm -f "$DIR/on"; stop_audio; echo "voice off"; else touch "$DIR/on"; echo "voice on"; fi ;;
  *)      echo "usage: /talk [on|off|stop|status|quiet]"; exit 1 ;;
esac
