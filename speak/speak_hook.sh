#!/bin/bash
# Claude Code Stop hook: when voice replies are on, read Claude's last reply aloud with a local Kokoro voice.
# Toggle with /talk. Runs in the background so it never blocks the session; a new reply cuts off the old one.
# Settings (one value per file in ~/.claude/chief-speak/): voice, speed, loudness.
DIR="$HOME/.claude/chief-speak"
[ -f "$DIR/on" ] || exit 0
[ -f "$DIR/skip_once" ] && { rm -f "$DIR/skip_once"; exit 0; }

TTS="$(command -v mlx_audio.tts.generate || echo "$HOME/.local/bin/mlx_audio.tts.generate")"
MODEL="mlx-community/Kokoro-82M-bf16"
# Settings are validated: only a Kokoro voice id and plain numbers are ever passed on.
VOICE=$(cat "$DIR/voice" 2>/dev/null); [[ "$VOICE" =~ ^[a-z]{2}_[a-z]+$ ]] || VOICE=bm_george
SPEED=$(cat "$DIR/speed" 2>/dev/null); [[ "$SPEED" =~ ^[0-9]+(\.[0-9]+)?$ ]] || SPEED=1.0
LUFS=$(cat "$DIR/loudness" 2>/dev/null); [[ "$LUFS" =~ ^-[0-9]+(\.[0-9]+)?$ ]] || LUFS=-14

text=$(jq -r '.last_assistant_message // empty' | python3 -I "$DIR/speak.py")
[ -n "$text" ] || exit 0

(
  [ -f "$DIR/play.pid" ] && kill "$(cat "$DIR/play.pid")" 2>/dev/null
  out="$DIR/tmp"; mkdir -p -m 700 "$out"
  HF_HUB_OFFLINE=1 "$TTS" --model "$MODEL" --voice "$VOICE" --speed "$SPEED" --text "$text" \
    --output_path "$out" --file_prefix reply --audio_format wav --join_audio >/dev/null 2>&1 || exit 0
  # Raise only this voice to a set loudness (raw Kokoro is ~-25 LUFS); system volume is never touched.
  play="$out/reply.wav"
  ffmpeg -y -loglevel error -i "$out/reply.wav" -af "loudnorm=I=$LUFS:TP=-1:LRA=11" -ar 24000 "$out/reply_loud.wav" \
    && play="$out/reply_loud.wav"
  afplay "$play" &
  echo $! > "$DIR/play.pid"
  wait
  rm -f "$DIR/play.pid"
) >/dev/null 2>&1 &
exit 0
