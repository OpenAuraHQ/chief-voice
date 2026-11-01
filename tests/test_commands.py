"""Self-test for Chief's command logic. No microphone, no typing: `python tests/test_commands.py`."""
import os
import sys
import tempfile

os.environ.setdefault("CHIEF_HOME", tempfile.mkdtemp())
os.environ.pop("CHIEF_LOG_TEXT", None)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import chief  # noqa: E402


def run(utterances):
    sent, windows = [], []
    c = chief.Chief(inject=sent.append, interrupt=lambda: sent.append("<ESC>"), window=windows.append)
    c.cue = lambda cmd: None
    for u in utterances:
        c.handle(u)
    return c, sent, windows


def check(name, got, want):
    if got != want:
        print(f"FAIL {name}: got {got!r}, want {want!r}")
        sys.exit(1)
    print(f"ok   {name}")


_, sent, _ = run(["Chief, open the notes app.", "and make a list", "Chief send."])
check("bare Chief starts a message, send types it", sent, ["open the notes app and make a list"])

_, sent, _ = run(["Chief listen", "hello there", "Chief send"])
check("'Chief listen' still works", sent, ["hello there"])

_, sent, _ = run(["Chief, first idea", "Chief delete", "second idea", "Chief send"])
check("delete clears the draft", sent, ["second idea"])

_, sent, _ = run(["Chief, never mind", "Chief cancel", "Chief send"])
check("cancel discards", sent, [])

_, sent, _ = run(["Chief, I need a Chief stop command for the app", "Chief send"])
check("a command mid-sentence stays text", sent, ["I need a Chief stop command for the app"])

_, sent, _ = run(["Chief stop"])
check("stop interrupts without a message", sent, ["<ESC>"])

_, sent, _ = run(["Chief sleep", "Chief, do something", "Chief send", "Chief wake", "Chief, now", "Chief send"])
check("asleep ignores everything until wake", sent, ["now"])

_, sent, _ = run(["the chief of staff called", "chief send"])
check("'chief' mid-sentence does not start a message", sent, [])

_, sent, _ = run(["Chiefs end"])
check("misheard 'Chiefs end' while idle does nothing", sent, [])

_, sent, _ = run(["Chief, hello", "Chiefs end."])
check("misheard 'Chiefs end' sends", sent, ["hello"])

c, sent, windows = run(["Chief, main terminal away.", "Chief, keep going", "Chief send", "Chief, main window back up"])
check("main terminal away / up", windows, ["away", "up"])
check("dictation continues while away", sent, ["keep going"])

c, sent, windows = run(["Chief listen, main terminal away", "status please", "Chief send"])
check("'Chief listen, main terminal away' keeps listening", (windows, sent), (["away"], ["status please"]))

_, sent, _ = run(["Chief, here is a long thought", "and then I said Chief in the middle", "Chief, more words", "Chief send"])
check("saying Chief mid-message never restarts it", sent, ["here is a long thought and then I said Chief in the middle Chief, more words"])

check("leading '!' is removed (Claude Code shell escape)", chief.safe_message("! rm -rf ~"), "rm -rf ~")
check("AppleScript string escaping", chief._as_string('say "hi" \\ café'), '"say \\"hi\\" \\\\ café"')

import io  # noqa: E402

import numpy as np  # noqa: E402

# A room whose noise (-50 dB) sits above the built-in mic's fixed gate (-52 dB): each burst of speech must still
# end on its own, not run to MAX_UTTER.
rng = np.random.default_rng(0)
noise = lambda n: rng.normal(0, 10 ** (-50 / 20), n)  # noqa: E731
t = np.arange(int(chief.SR * 1.5)) / chief.SR
parts = [noise(chief.SR * 4)]
for _ in range(4):
    parts += [noise(len(t)) + 10 ** (-34 / 20) * np.sqrt(2) * np.sin(2 * np.pi * 220 * t), noise(len(t))]
pcm = (np.clip(np.concatenate(parts), -1, 1) * 32767).astype(np.int16).tobytes()
chief.claude_speaking = lambda: False
lengths = [len(u) / chief.SR for u in chief.utterances(io.BytesIO(pcm), chief.SPEECH_DB_BUILTIN)]
check("a noisy room still ends each utterance", sum(2 <= d <= 4 for d in lengths) == 4 and max(lengths) < 5, True)

# "main terminal away", then that window is closed: a send goes to the front window, not nowhere.
calls, real_osa = [], chief._osa
chief._osa = lambda script: calls.append(script) or ("/dev/ttys001" if "tty of every tab" in script else "")
chief._remember("/dev/ttys009")
chief.inject_terminal("hello")
chief._osa = real_osa
check("a closed away window falls back to the front window",
      (chief.MAIN["tty"], any("System Events" in c for c in calls)), (None, True))

with open(chief.LOG) as f:
    log = f.read()
check("dictated words stay out of the log by default", "notes app" in log or "keep going" in log, False)
print("all tests passed")
