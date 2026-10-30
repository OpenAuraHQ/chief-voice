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

check("leading '!' is removed (Claude Code shell escape)", chief.safe_message("! rm -rf ~"), "rm -rf ~")
check("AppleScript string escaping", chief._as_string('say "hi" \\ café'), '"say \\"hi\\" \\\\ café"')

with open(chief.LOG) as f:
    log = f.read()
check("dictated words stay out of the log by default", "notes app" in log or "keep going" in log, False)
print("all tests passed")
