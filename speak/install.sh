#!/bin/zsh
# Optional add-on: Claude reads its replies aloud with a local Kokoro voice, toggled with /talk.
# Usage: speak/install.sh            install (safe to re-run)
#        speak/install.sh --remove   remove the hook, the /talk command and the add-on's files
set -euo pipefail
SRC="${0:A:h}"
DEST="$HOME/.claude/chief-speak"
SETTINGS="$HOME/.claude/settings.json"
HOOK_CMD="$DEST/speak_hook.sh"
say_step() { print -P "%F{cyan}==>%f $1"; }
fail() { print -P "%F{red}x%f $1"; exit 1; }

if [[ "${1:-}" == "--remove" ]]; then
  if [[ -f "$SETTINGS" ]]; then
    cp "$SETTINGS" "$SETTINGS.bak-chief-speak"
    jq --arg c "$HOOK_CMD" '
      if .hooks.Stop then .hooks.Stop |= map(.hooks |= map(select(.command != $c)) | select(.hooks | length > 0)) else . end
      | if .hooks.Stop == [] then del(.hooks.Stop) else . end' "$SETTINGS.bak-chief-speak" > "$SETTINGS"
  fi
  rm -rf "$DEST" "$HOME/.claude/commands/talk.md"
  echo "Voice replies removed (settings backup: $SETTINGS.bak-chief-speak)"
  exit 0
fi

say_step "Checking tools"
[[ "$(uname -m)" == "arm64" ]] || fail "Needs Apple silicon (Kokoro runs on the Mac's GPU through MLX)."
for t in jq ffmpeg uv; do command -v $t >/dev/null || fail "$t is missing. Install it with:  brew install $t"; done

say_step "Installing the voice engine (mlx-audio, pinned)"
uv tool install --quiet --force "mlx-audio==0.6.3" --with "misaki[en]==0.9.4" \
  --with "en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"

say_step "Copying the add-on to $DEST"
mkdir -p -m 700 "$DEST" "$HOME/.claude/commands"
cp "$SRC/speak_hook.sh" "$SRC/speak.py" "$SRC/talk.sh" "$DEST/"
chmod 700 "$DEST/speak_hook.sh" "$DEST/talk.sh"
cp "$SRC/talk.md" "$HOME/.claude/commands/talk.md"
[[ -f "$DEST/voice" ]] || echo bm_george > "$DEST/voice"
[[ -f "$DEST/speed" ]] || echo 1.2 > "$DEST/speed"
[[ -f "$DEST/loudness" ]] || echo -14 > "$DEST/loudness"

say_step "Downloading the voice model (Kokoro 82M, one time)"
"$(command -v mlx_audio.tts.generate || echo "$HOME/.local/bin/mlx_audio.tts.generate")" \
  --model mlx-community/Kokoro-82M-bf16 --voice bm_george --text "Voice replies are ready." \
  --output_path "$DEST/tmp" --file_prefix test --audio_format wav --join_audio >/dev/null 2>&1 \
  && afplay "$DEST/tmp/test.wav" || fail "The voice model did not run; see the command above."

say_step "Adding the Stop hook to $SETTINGS"
[[ -f "$SETTINGS" ]] || echo '{}' > "$SETTINGS"
cp "$SETTINGS" "$SETTINGS.bak-chief-speak"
jq --arg c "$HOOK_CMD" '
  if ([.hooks.Stop[]?.hooks[]?.command] | index($c)) then .
  else .hooks.Stop = ((.hooks.Stop // []) + [{"hooks": [{"type": "command", "command": $c, "async": true, "timeout": 120}]}]) end
' "$SETTINGS.bak-chief-speak" > "$SETTINGS"
jq -e . "$SETTINGS" >/dev/null || { cp "$SETTINGS.bak-chief-speak" "$SETTINGS"; fail "settings.json did not validate; restored the backup"; }

cat <<EOF

Voice replies installed (off until you turn them on).
  /talk         toggle spoken replies in Claude Code     /talk stop   cut off the current reply
  Voice:        echo af_heart > $DEST/voice   (Kokoro voices: af_heart, am_michael, bm_george, ...)
  Speed:        echo 1.5 > $DEST/speed
  Loudness:     echo -11 > $DEST/loudness     (closer to 0 is louder)
If the hook does not fire in an open session, open /hooks once or restart Claude Code.
EOF
