# Setting up Chief (instructions for a Claude agent)

You are setting up Chief, a local voice-control tool for Claude Code, on the user's Mac. Follow these steps in order, verify each one, and tell the user plainly what you did and what they must click themselves. Read README.md for the user-facing details.

## Ground rules

- Run everything from this repository's folder. Do not edit `chief.py` or `mic_feed.py` to "fix" a setup problem; setup problems are permissions, devices or settings.
- Never loosen the safety rules in `chief.py` (`safe_message`, offline mode, private file modes, text-free logs) unless the user explicitly asks and understands the change.
- Do not set `CHIEF_LOG_TEXT=1` unless the user asks for it.
- macOS permission prompts can only be accepted by the user. Tell them exactly which prompt to expect and what to click; never try to automate those dialogs.

## 1. Check the machine

```bash
uname -m                       # must be arm64 (Apple silicon)
sw_vers -productVersion        # macOS 14 or newer
command -v ffmpeg uv python3   # ffmpeg is required; uv or Python 3.11+ is required
```

If `ffmpeg` or `uv` is missing, ask the user before running `brew install ffmpeg uv` (it installs software system-wide).

## 2. Install

```bash
./install.sh
```

It creates `.venv`, installs the pinned packages, downloads the Whisper model (about 1.6 GB, a few minutes), runs `tests/test_commands.py`, and lists the microphones. It must end with "all tests passed" and "Installed". If a step fails, report the exact error to the user instead of working around it.

## 3. Pick the microphone

Show the user the microphone list from the installer. If they use an external mic (a wireless lavalier, USB mic, headset), save part of its name:

```bash
mkdir -p ~/.chief && echo 'CHIEF_MIC="<part of the name>"' >> ~/.chief/config.env
```

Otherwise leave it automatic (system input, never an iPhone).

## 4. Start and grant permissions

```bash
./chief.sh on
./chief.sh status        # expect "Chief is on" and a "mic: <name>" line
```

Then tell the user, in this order:

1. If macOS asks for Microphone access for their terminal app, click Allow.
2. With a Claude Code window in front, say: "Chief, this is a test." pause, "Chief send."
3. macOS will ask to let the terminal control "System Events" and "Terminal": click OK for both. If keystrokes still do not arrive, add the terminal app under System Settings > Privacy & Security > Accessibility, then run `./chief.sh restart`.

Verify with `./chief.sh status`: the log should show `[listen]`, `[send]` and `SEND <n chars>`, and the test sentence should have appeared in Claude Code.

## 5. Optional

- Start at login: `./chief.sh autostart on`
- Voice replies: `speak/install.sh` (needs `jq`; ask before `brew install jq`). It adds a Stop hook to `~/.claude/settings.json` (backup written first) and a `/talk` command. Replies stay silent until the user runs `/talk`. If the hook does not fire in an already-open session, tell the user to open `/hooks` once or restart Claude Code.
- tmux users: `.venv/bin/python chief.py --tmux <session>` instead of `./chief.sh on`.

## Troubleshooting checklist

| Symptom | Check |
|---|---|
| `Chief failed to start` | `tail -20 ~/.chief/chief.out` |
| No `[listen]` in the log when the user speaks | Microphone permission; wrong mic (`CHIEF_MIC`); speech gate (`CHIEF_SPEECH_DB=-50` in `~/.chief/config.env`) |
| `[send]` logged but nothing typed | Accessibility and Automation permissions for the terminal app; restart Chief after granting |
| Wake word misheard | add the mishearing to `CHIEF_WAKE` (comma list) |

Report back to the user: what is installed, where (`<this folder>`, `~/.chief`), how to turn it on and off, and anything they still need to click.
