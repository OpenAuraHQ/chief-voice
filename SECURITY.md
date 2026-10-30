# Security

Chief listens to a microphone and types into a terminal that runs an AI agent, so it is built to do as little as possible with what it hears.

## What it can and cannot do

| | |
|---|---|
| Network | none at runtime. Models download once at install; Chief and the voice add-on then run with `HF_HUB_OFFLINE=1` |
| Audio | held in memory only, never written to disk |
| Text | written to the log only as commands and message lengths, unless `CHIEF_LOG_TEXT=1` |
| Where it types | only the Claude Code window: the front Terminal window, the window sent away with "main terminal away", or the tmux session you name |
| What it types | your dictated message plus Return, or Escape for "stop". A leading `!` (Claude Code's shell escape) is always removed |
| Files | `~/.chief` (mode 700; log, state and settings mode 600). The voice add-on uses `~/.claude/chief-speak` and adds one Stop hook to `~/.claude/settings.json`, with a backup |

## Things to know

- Anyone who can speak into the microphone can dictate to your Claude Code session after saying "Chief". Use `Chief sleep`, `./chief.sh off`, or a close-talking mic in shared spaces.
- Claude Code's own permission settings still apply to whatever you dictate. Chief does not bypass them.
- The voice add-on reads Claude's replies aloud through your speakers or headphones.
- Dependencies are pinned in `requirements.txt` and `speak/install.sh`. Review changes to those pins.

## Reporting a problem

Open a private security advisory on this repository (Security > Report a vulnerability), or email the maintainers listed on the OpenAuraHQ organization page. Please do not open a public issue for a vulnerability.
