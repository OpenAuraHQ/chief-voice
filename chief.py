#!/usr/bin/env python3
"""Chief: hands-free voice control for Claude Code on macOS.

Listens on a microphone, transcribes each utterance locally with Whisper (MLX, Apple silicon), and reacts
to spoken commands. Nothing leaves the machine: no audio, transcript or telemetry is sent anywhere.

    "Chief, <words>"            start a message; the words after "Chief" are kept ("Chief listen" also works)
    "Chief send"                type the message into Claude Code, press Return, stop listening
    "Chief delete"              clear the message, keep listening ("Chief scratch" also works)
    "Chief cancel"              stop listening, discard the message
    "Chief stop"                press Escape in Claude Code to interrupt it (works listening or not)
    "Chief sleep"               ignore everything, drop any message, until "Chief wake"
    "Chief wake"                commands work again ("Chief wake up", "wake up Chief" also work)
    "Chief, main terminal away" minimize the Claude Code window; while it is away, "send" and "stop" still
                                reach it, typed straight into that window (no focus needed)
    "Chief, main terminal up"   bring that window back to the front ("window" works for "terminal")

Commands fire only at the END of an utterance (a pause after them), so a command named mid-sentence
("I need a Chief stop command") stays part of the message. A bare "Chief" starts a message only at the
start of an utterance.

Usage:
    python chief.py                 live; types into Terminal.app (front window, or the "away" window)
    python chief.py --tmux NAME     live; types into tmux session NAME instead (no focus needed)
    python chief.py --file a.wav    run a recording through the same logic (dry run, nothing is typed)

Settings (environment variables, all optional): see README.md.
"""
import argparse
import collections
import json
import os
import re
import subprocess
import sys
import threading
import time

import mlx_whisper
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # own folder, also under python -I
from mic_feed import ffmpeg_from_mic, input_names  # noqa: E402

# --- settings ------------------------------------------------------------------------------------------
HOME = os.path.expanduser(os.environ.get("CHIEF_HOME", "~/.chief"))
os.makedirs(HOME, mode=0o700, exist_ok=True)
STATE = os.path.join(HOME, "state.json")
LOG = os.path.join(HOME, "chief.log")
AWAY_FILE = os.path.join(HOME, "away_tty")
MIC = os.environ.get("CHIEF_MIC", "")                  # part of an input device name; empty = automatic
MODEL = os.environ.get("CHIEF_MODEL", "mlx-community/whisper-large-v3-turbo")
LOG_TEXT = os.environ.get("CHIEF_LOG_TEXT") == "1"     # write dictated words to the log (off by default)
SOUNDS_ON = os.environ.get("CHIEF_SOUNDS", "1") != "0"
SPEECH_DB = float(os.environ.get("CHIEF_SPEECH_DB", "-45"))   # frame level that counts as speech
SPEECH_DB_BUILTIN = -52.0  # the built-in mic picks speech up ~7 dB lower
WAKE_WORDS = os.environ.get("CHIEF_WAKE", "chief,cheif,chiefs,chief's,cheap")  # Whisper's common mishearings

SR = 16000
FRAME = SR * 30 // 1000  # 30 ms
END_SILENCE = 0.8  # seconds of quiet that closes an utterance
MIN_SPEECH = 0.35  # shorter blips are ignored
MAX_UTTER = 25.0
# The gate stays at least this many dB above the room's quiet level, so a fan or AC never holds an utterance open
NOISE_MARGIN = float(os.environ.get("CHIEF_NOISE_MARGIN", "8"))

# --- command grammar -----------------------------------------------------------------------------------
WAKE = r"(?:" + "|".join(re.escape(w.strip()) for w in WAKE_WORDS.split(",") if w.strip()) + r")"
COMMANDS = {"listen": "listen", "send": "send", "sent": "send", "scent": "send", "sand": "send",
            "cent": "send", "said": "send", "delete": "delete", "scratch": "delete", "cancel": "cancel",
            "stop": "stop", "sleep": "sleep"}
# Whisper's mishearings of "Chief send": "Chiefs End", "Chiefsend", "Chiefsand", "Chiefs and"
SPLIT_SEND = re.compile(r"\b(chief)'?s[\s,.-]*(?:ends?|and)\b|\b(chief)s?sand\b", re.I)
CMD = WAKE + r"[\s,.!?-]*(" + "|".join(COMMANDS) + r")\b"
LISTEN_RE = re.compile(r"(?:" + WAKE + r"[\s,.!?-]*listen|\blisten[\s,.!?-]*" + WAKE + r")\b[.!?,]*", re.I)
WAKE_RE = re.compile(r"(?:" + WAKE + r"[\s,.!?-]*(?:wake|awake)(?:[\s,.!?-]*up)?|\bwake[\s,.!?-]*up[\s,.!?-]*"
                     + WAKE + r")\b[.!?,]*", re.I)
# A bare "Chief" at the start of an utterance starts a message, unless a command follows it.
START_RE = re.compile(r"^\W*(?:hey\s+|okay\s+|ok\s+)?" + WAKE + r"\b(?![\s,.!?-]*(?:" + "|".join(COMMANDS)
                      + r"|wake|awake|(?:the\s+)?(?:main\s+)?(?:terminal|window))\b)[\s,.!?-]*", re.I)
# "Chief, main terminal away / up" ("window" works too, and "main terminal away" right after "Chief listen").
TERM_RE = re.compile(r"(.*?)(?:\b" + WAKE + r"[\s,.!?-]*(?:the\s+)?(?:main\s+)?|\b(?:the\s+)?main\s+)"
                     r"(?:terminal|window)[\s,.!?-]*(away|down|hide|up|back|show)\b(?:[\s,.-]*up)?[\s.!?,]*$",
                     re.I | re.S)
END_RE = re.compile(r"(.*?)" + CMD + r"[\s.!?,]*$", re.I | re.S)

SOUNDS = {
    "listen": "/System/Library/Sounds/Tink.aiff",
    "send": "/System/Library/Sounds/Glass.aiff",
    "delete": "/System/Library/Sounds/Pop.aiff",
    "cancel": "/System/Library/Sounds/Bottle.aiff",
    "stop": "/System/Library/Sounds/Funk.aiff",
    "sleep": "/System/Library/Sounds/Submarine.aiff",
    "wake": "/System/Library/Sounds/Hero.aiff",
    "away": "/System/Library/Sounds/Pop.aiff",
    "up": "/System/Library/Sounds/Pop.aiff",
}


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, flush=True)
    fd = os.open(LOG, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(line + "\n")


def said(text):
    """What may go in the log for dictated words: the words only if CHIEF_LOG_TEXT=1."""
    return text if LOG_TEXT else f"<{len(text)} chars>"


def safe_message(msg):
    """Claude Code treats a leading '!' as a shell command; a spoken message never needs one."""
    return msg.lstrip("! ").strip()


class Chief:
    def __init__(self, inject, interrupt, window=None, dry=False):
        self.listening = False
        self.asleep = False
        self.draft = []
        self.inject = inject
        self.interrupt = interrupt
        self.window = window or (lambda cmd: None)
        self.dry = dry
        self.write_state("")

    def write_state(self, heard):
        """Small status file for status bars or menus (private to this user)."""
        tmp = STATE + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"listening": self.listening, "asleep": self.asleep, "draft": " ".join(self.draft),
                       "heard": heard if self.listening else "", "away": MAIN["tty"] is not None,
                       "t": time.time()}, f)
        os.replace(tmp, STATE)

    def cue(self, cmd):
        if not self.dry and SOUNDS_ON:
            subprocess.Popen(["afplay", SOUNDS[cmd]])

    def handle(self, text):
        """Apply one transcribed utterance, in order, command by command."""
        text = SPLIT_SEND.sub("chief send", text)
        if self.asleep:  # asleep: only "Chief wake", anywhere in the utterance, does anything
            m = WAKE_RE.search(text)
            if not m:
                return
            self.command("wake")
            text = text[m.end():]
        if not self.listening:  # while off, "Chief listen" anywhere, or a bare "Chief" at the start
            m = LISTEN_RE.search(text) or START_RE.match(text)
            if m:
                self.command("listen")
                text = text[m.end():]
        else:  # while on, "Chief listen" only at the very start (restarts the message)
            m = LISTEN_RE.match(text.lstrip())
            if m:
                self.command("listen")
                text = text.lstrip()[m.end():]
        term = TERM_RE.match(text)
        if term:  # main terminal away / up: keeps the listening state, so dictation carries on
            self.add(term.group(1))
            self.command("away" if term.group(2).lower() in ("away", "down", "hide") else "up")
            self.write_state(text)
            return
        end = END_RE.match(text)
        if end and COMMANDS[end.group(2).lower()] != "listen":
            self.add(end.group(1))
            self.command(COMMANDS[end.group(2).lower()])
        else:
            self.add(text)
        self.write_state(text)

    def add(self, chunk):
        chunk = chunk.strip(" ,.;:-")
        if self.listening and chunk:
            self.draft.append(chunk)
            log(f"+ {said(chunk)}")

    def command(self, cmd):
        log(f"[{cmd}]")
        if cmd == "listen":
            self.listening = True
            self.draft = []
        elif cmd == "sleep":
            self.asleep = True
            self.listening = False
            self.draft = []
        elif cmd == "wake":
            self.asleep = False
        elif cmd == "stop":
            if not self.dry:
                self.interrupt()
        elif cmd in ("away", "up"):
            if not self.dry:
                self.window(cmd)
        elif not self.listening:
            return  # send/delete/cancel only mean something while listening
        elif cmd == "delete":
            self.draft = []
        elif cmd == "cancel":
            self.listening = False
            self.draft = []
        elif cmd == "send":
            msg = safe_message(" ".join(self.draft))
            self.listening = False
            self.draft = []
            if msg:
                log(f"SEND {said(msg)}")
                if not self.dry:
                    self.inject(msg)
        self.cue(cmd)


# --- Terminal.app --------------------------------------------------------------------------------------
# The Claude Code window sent away with "main terminal away": its tty while minimized, else None.
MAIN = {"tty": None}
try:
    MAIN["tty"] = open(AWAY_FILE).read().strip() or None
except OSError:
    pass


def _remember(tty):
    MAIN["tty"] = tty
    if tty:
        fd = os.open(AWAY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(tty)
    elif os.path.exists(AWAY_FILE):
        os.remove(AWAY_FILE)


def _as_string(text):
    """An AppleScript string literal (escapes backslash and double quote; Unicode passes through)."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _osa(script):
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode:
        log(f"osascript failed: {r.stderr.strip()}")
    return r.stdout.strip()


def _away_tab():
    return f'(selected tab of (first window whose tty of selected tab is {_as_string(MAIN["tty"])}))'


def terminal_window(cmd):
    """away: remember the front Terminal window's tty and minimize it. up: restore that window to the front."""
    if cmd == "away":
        tty = _osa('tell application "Terminal" to get tty of selected tab of front window')
        if re.fullmatch(r"/dev/ttys\d+", tty or ""):
            _remember(tty)
            _osa(f'tell application "Terminal" to set miniaturized of (first window whose tty of selected tab '
                 f'is {_as_string(tty)}) to true')
            log("main terminal away")
        return
    tty = MAIN["tty"]
    _remember(None)
    if tty:
        _osa('tell application "Terminal"\n'
             f'  set w to (first window whose tty of selected tab is {_as_string(tty)})\n'
             '  set miniaturized of w to false\n  set index of w to 1\n  activate\nend tell')
        log("main terminal up")
    else:
        _osa('tell application "Terminal" to activate')


def _forget_closed_window():
    """If the window sent away has since been closed, fall back to the front window instead of typing nowhere."""
    if not MAIN["tty"]:
        return
    out = _osa('tell application "Terminal" to get tty of every tab of every window')
    if MAIN["tty"] not in {t.strip() for t in out.split(",")}:
        log("the away window was closed; typing into the front window")
        _remember(None)


def inject_terminal(msg):
    """Type into Claude Code and press Return: into the away window if one is away, else the front window."""
    _forget_closed_window()
    if MAIN["tty"]:  # Terminal's `do script` types into a tab without focusing or un-minimizing it
        # It sends the words and a Return in one burst, which Claude Code reads as a paste (the Return becomes
        # a new line). So the words go first, then after a pause a lone Return submits them.
        _osa(f'tell application "Terminal" to do script {_as_string(msg)} in {_away_tab()}')
        time.sleep(0.8 + len(msg) / 300)  # long messages take Claude Code longer to take in
        _osa(f'tell application "Terminal" to do script "" in {_away_tab()}')
        # A long message takes the first Return as a new line; the second submits it. On an empty box
        # (a short message already sent) the extra Return does nothing.
        time.sleep(0.8)
        _osa(f'tell application "Terminal" to do script "" in {_away_tab()}')
        return
    _osa('tell application "Terminal" to activate\n'
         'delay 0.15\n'
         'tell application "System Events"\n'
         f'  keystroke {_as_string(msg)}\n'
         '  delay 0.25\n'
         '  key code 36\n'
         'end tell')


def interrupt_terminal():
    """Press Escape in Claude Code (interrupts it): the away window if one is away, else the front window."""
    _forget_closed_window()
    if MAIN["tty"]:
        _osa(f'tell application "Terminal" to do script (ASCII character 27) in {_away_tab()}')
        return
    _osa('tell application "Terminal" to activate\n'
         'delay 0.15\n'
         'tell application "System Events" to key code 53')


# --- tmux ----------------------------------------------------------------------------------------------
def make_interrupt_tmux(target):
    return lambda: subprocess.run(["tmux", "send-keys", "-t", target, "Escape"])


def make_inject_tmux(target):
    def inject(msg):
        subprocess.run(["tmux", "send-keys", "-t", target, "-l", msg])
        time.sleep(0.25)
        subprocess.run(["tmux", "send-keys", "-t", target, "Enter"])
    return inject


# --- audio ---------------------------------------------------------------------------------------------
def transcribe(audio):
    peak = float(np.abs(audio).max()) if len(audio) else 0.0
    if peak > 1e-4:
        audio = audio * (0.7 / peak)  # same level into Whisper whatever the mic
    r = mlx_whisper.transcribe(audio, path_or_hf_repo=MODEL, language="en",
                               condition_on_previous_text=False, no_speech_threshold=0.6)
    return " ".join(s["text"].strip() for s in r["segments"]
                    if s.get("no_speech_prob", 0) < 0.6).strip()


VOICE_PID = os.path.expanduser("~/.claude/chief-speak/play.pid")  # written while a spoken reply plays (speak/)
_speak_cache = [0.0, False]


def claude_speaking():
    """True while Claude's spoken reply is playing, so Chief never transcribes Claude's own voice."""
    now = time.time()
    if now - _speak_cache[0] > 0.25:
        try:
            os.kill(int(open(VOICE_PID).read()), 0)
            _speak_cache[1] = True
        except Exception:
            _speak_cache[1] = False
        _speak_cache[0] = now
    return _speak_cache[1]


def utterances(stream, gate=SPEECH_DB):
    """Yield float32 arrays, one per spoken utterance, using an energy gate."""
    buf, speech, quiet, active = [], 0.0, 0.0, False
    pre = []  # keep 300 ms before speech starts so first words are not clipped
    recent = collections.deque(maxlen=300)  # last ~9 s of frame levels, to follow the room's noise floor
    room_gate, logged = gate, gate
    while True:
        raw = stream.read(FRAME * 2)
        if len(raw) < FRAME * 2:
            break
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        db = 20 * np.log10(np.sqrt(np.mean(x * x)) + 1e-9)
        dt = FRAME / SR
        if claude_speaking():  # drop anything heard while Claude talks (and the utterance in progress)
            active, buf, quiet, pre = False, [], 0.0, []
            continue
        recent.append(db)
        if len(recent) >= 30 and len(recent) % 10 == 0:
            # A noisy room can sit above the fixed gate; then an utterance never ends until MAX_UTTER.
            room_gate = max(gate, float(np.percentile(recent, 20)) + NOISE_MARGIN)
            if abs(room_gate - logged) >= 3:
                log(f"speech gate {room_gate:.0f} dB (room noise)")
                logged = room_gate
        if db > room_gate:
            if not active:
                active, buf, speech = True, list(pre), 0.0
            speech += dt
            quiet = 0.0
        elif active:
            quiet += dt
        if active:
            buf.append(x)
            dur = len(buf) * dt
            if quiet >= END_SILENCE or dur >= MAX_UTTER:
                if speech >= MIN_SPEECH:
                    yield np.concatenate(buf)
                active, buf, quiet = False, [], 0.0
        else:
            pre = (pre + [x])[-10:]
    if active and speech >= MIN_SPEECH:
        yield np.concatenate(buf)


def ffmpeg_reader(args):
    out = ["-af", "highpass=f=80", "-ac", "1", "-ar", str(SR), "-f", "s16le", "pipe:1"]
    if args.file:
        cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-i", args.file, *out]
        return subprocess.Popen(cmd, stdout=subprocess.PIPE).stdout, SPEECH_DB_BUILTIN if args.builtin else SPEECH_DB
    proc = ffmpeg_from_mic(MIC, out)
    log(f"mic: {proc.device}")
    watch_devices(proc.device)
    return proc.stdout, (SPEECH_DB_BUILTIN if proc.builtin else SPEECH_DB)


def watch_devices(current):
    """Restart when mics change: the chosen mic (CHIEF_MIC) arrives, or the mic in use disappears."""
    def loop():
        while True:
            time.sleep(3)
            try:
                names = input_names()
            except Exception:
                continue
            wanted_back = bool(MIC) and MIC.lower() not in current.lower() and any(MIC.lower() in n.lower() for n in names)
            gone = current not in names
            if wanted_back or gone:
                log("mics changed, restarting")
                os.execv(sys.executable, [sys.executable] + sys.argv)
    threading.Thread(target=loop, daemon=True).start()


def main():
    ap = argparse.ArgumentParser(description="Chief: hands-free voice control for Claude Code")
    ap.add_argument("--file", help="run a recording through the command logic (dry run)")
    ap.add_argument("--tmux", help="type into this tmux session instead of Terminal.app")
    ap.add_argument("--builtin", action="store_true", help="with --file: use the built-in-mic speech gate")
    args = ap.parse_args()
    if args.tmux:
        chief = Chief(make_inject_tmux(args.tmux), make_interrupt_tmux(args.tmux), dry=bool(args.file))
    else:
        chief = Chief(inject_terminal, interrupt_terminal, window=terminal_window, dry=bool(args.file))
    transcribe(np.zeros(SR // 2, dtype=np.float32))  # load the model before listening
    log(f"ready ({'file ' + args.file if args.file else 'microphone'})")
    for audio in utterances(*ffmpeg_reader(args)):
        text = transcribe(audio)
        if not text:
            continue
        if chief.listening:  # while off, nothing heard is written down
            log(f"heard {said(text)}")
        chief.handle(text)


if __name__ == "__main__":
    sys.exit(main())
