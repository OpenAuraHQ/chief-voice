# Chief

Hands-free voice control for [Claude Code](https://claude.com/claude-code) on a Mac. Say "Chief", talk, say "Chief send", and your words are typed into Claude Code. Speech is turned into text on your Mac with Whisper running on the GPU. Nothing is uploaded.

Optional add-on: Claude reads its replies back to you in a natural local voice (Kokoro), toggled with `/talk`.

## Requirements

| | |
|---|---|
| Mac | Apple silicon (M1 or newer), macOS 14+ |
| Tools | [Homebrew](https://brew.sh) `ffmpeg`, and either `uv` or Python 3.11+ |
| Terminal | Terminal.app (or any terminal through tmux, see below) |
| Disk | about 2 GB (speech model 1.6 GB) |

## Install

```bash
brew install ffmpeg uv
git clone https://github.com/OpenAuraHQ/chief-voice.git
cd chief-voice
./install.sh          # private Python environment, pinned packages, model download, self-test
./chief.sh on         # start listening
```

On first use macOS asks for three permissions. Allow each, for the terminal app you started Chief from:

| Permission | Why | Where |
|---|---|---|
| Microphone | hear you | System Settings > Privacy & Security > Microphone |
| Accessibility | press keys in Claude Code | System Settings > Privacy & Security > Accessibility |
| Automation (Terminal, System Events) | type into the right window | asked automatically on the first "Chief send" |

## Commands

| Say | Does |
|---|---|
| "Chief, ..." | start a message; the words after "Chief" are kept |
| "Chief send" | type the message into Claude Code and press Return |
| "Chief delete" (or "scratch") | clear the message, keep listening |
| "Chief cancel" | stop listening, discard the message |
| "Chief stop" | press Escape to interrupt Claude (works any time) |
| "Chief sleep" / "Chief wake" | ignore everything until woken |
| "Chief, main terminal away" | minimize the Claude Code window; "send" and "stop" still reach it |
| "Chief, main terminal up" | bring that window back ("window" works for "terminal") |

Commands only count at the end of what you say, after a short pause. "I need a Chief stop command" stays part of your message. You hear a short sound for each command.

Example: "Chief, summarize the last commit and suggest a test." (pause) "Chief send."

## Everyday use

| | |
|---|---|
| `./chief.sh on` / `off` / `restart` | start or stop Chief |
| `./chief.sh status` | is it running, last few events |
| `./chief.sh log` | follow the event log |
| `./chief.sh autostart on` / `off` | start Chief at every login |

## Settings

Put any of these in `~/.chief/config.env` (one `NAME="value"` per line), then `./chief.sh restart`.

| Setting | Default | |
|---|---|---|
| `CHIEF_MIC` | automatic | part of a microphone's name, e.g. `"Wireless Microphone"`. Automatic = the system input, never an iPhone; Chief switches back when that mic is plugged in again |
| `CHIEF_WAKE` | `chief,cheif,chiefs,chief's,cheap` | the wake word and how Whisper tends to mishear it |
| `CHIEF_MODEL` | `mlx-community/whisper-large-v3-turbo` | any MLX Whisper model (re-run `./install.sh` after changing) |
| `CHIEF_SOUNDS` | `1` | `0` turns the command sounds off |
| `CHIEF_SPEECH_DB` | `-45` | speech gate; lower it (e.g. `-50`) if quiet speech is missed |
| `CHIEF_LOG_TEXT` | `0` | `1` also writes your dictated words to the log (off for privacy) |
| `CHIEF_HOME` | `~/.chief` | where the log, state and settings live |

### tmux instead of Terminal.app

`.venv/bin/python chief.py --tmux SESSION` types into a tmux session (works with any terminal app and without window focus). Window commands are Terminal.app only.

## Voice replies (optional)

```bash
speak/install.sh      # local Kokoro voice + a Claude Code Stop hook + the /talk command
```

In Claude Code: `/talk` toggles spoken replies, `/talk stop` cuts one off, `/talk quiet` skips the next. Code, tables, links and file paths are skipped so only the prose is read. Voice, speed and loudness are one-line files in `~/.claude/chief-speak/` (the installer prints how). Remove with `speak/install.sh --remove`.

## Privacy and security

- Speech never leaves the Mac. The models download once at install; afterwards Chief and the voice add-on run with `HF_HUB_OFFLINE=1`, so they make no network requests.
- No audio is stored. While Chief is not listening, nothing it hears is written anywhere. While it is, the log records commands and message lengths only, unless you set `CHIEF_LOG_TEXT=1`.
- Chief only types into Claude Code's window: the front Terminal window, or the window you sent away. A message can never start with `!` (Claude Code's shell escape).
- Logs, state and settings are private to your user account (`~/.chief`, mode 700).
- Dependencies are pinned in `requirements.txt`. See [SECURITY.md](SECURITY.md).

## Troubleshooting

| Problem | Fix |
|---|---|
| Nothing happens when you speak | `./chief.sh status`; check Microphone permission for your terminal; try `CHIEF_SPEECH_DB=-50` |
| It hears the wrong mic | set `CHIEF_MIC` (install.sh lists your microphones) |
| "Chief send" types nothing | allow Accessibility and Automation for your terminal, then `./chief.sh restart` |
| Your wake word is misheard as something else | add the mishearing to `CHIEF_WAKE` |

## How it works

`mic_feed.py` reads the microphone through CoreAudio (sounddevice) and streams it into ffmpeg. `chief.py` cuts the stream into utterances with an energy gate, transcribes each with MLX Whisper, and runs it through a small command grammar. Typing goes through AppleScript: keystrokes into the front Terminal window, or Terminal's `do script` into a minimized one. The self-test (`tests/test_commands.py`) covers the grammar and the safety rules.

## Uninstall

```bash
./chief.sh autostart off; ./chief.sh off
speak/install.sh --remove     # if you installed voice replies
rm -rf ~/.chief  /path/to/chief
```

## License

MIT, see [LICENSE](LICENSE).
