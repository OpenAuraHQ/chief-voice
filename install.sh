#!/bin/zsh
# Chief installer: checks the Mac, creates a private virtual environment with pinned packages,
# downloads the speech model once, and runs the self-test. Safe to re-run.
set -euo pipefail
DIR="${0:A:h}"
cd "$DIR"
say_step() { print -P "%F{cyan}==>%f $1"; }
fail() { print -P "%F{red}x%f $1"; exit 1; }

say_step "Checking this Mac"
[[ "$(uname -s)" == "Darwin" ]] || fail "Chief runs on macOS only."
[[ "$(uname -m)" == "arm64" ]] || fail "Chief needs Apple silicon (M1 or newer): Whisper runs on the Mac's GPU through MLX."
command -v ffmpeg >/dev/null || fail "ffmpeg is missing. Install it with:  brew install ffmpeg"

say_step "Creating the Python environment (.venv)"
if command -v uv >/dev/null; then
  uv venv --python 3.12 --quiet .venv
  uv pip install --quiet --python .venv/bin/python -r requirements.txt
else
  PYTHON="$(command -v python3.12 || command -v python3.13 || command -v python3.11 || true)"
  [[ -n "$PYTHON" ]] || fail "Python 3.11+ is missing. Install it with:  brew install python@3.12   (or install uv)"
  "$PYTHON" -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -r requirements.txt
fi

say_step "Downloading the speech model (Whisper large-v3-turbo, about 1.6 GB, one time)"
MODEL="${CHIEF_MODEL:-mlx-community/whisper-large-v3-turbo}"
.venv/bin/python -I -c "
import numpy as np, mlx_whisper
mlx_whisper.transcribe(np.zeros(8000, dtype=np.float32), path_or_hf_repo='$MODEL', language='en')
print('model ready')"

say_step "Running the self-test"
CHIEF_HOME="$(mktemp -d)" .venv/bin/python -I tests/test_commands.py

say_step "Microphones macOS can see"
.venv/bin/python -I -c "
import sounddevice as sd
for d in sd.query_devices():
    if d['max_input_channels'] > 0: print('  -', d['name'])"

cat <<'EOF'

Installed. Next:
  1. ./chief.sh on            start listening (first start asks for Microphone access; allow it)
  2. Say "Chief, hello there" ... "Chief send" with a Claude Code window in front of you.
     macOS will ask to let your terminal control "System Events" and "Terminal": allow both
     (System Settings > Privacy & Security > Accessibility and Automation).
  3. Optional: ./chief.sh autostart on    start Chief at every login
     Optional: pick a specific mic: echo 'CHIEF_MIC="Wireless Microphone"' >> ~/.chief/config.env
EOF
