"""Gapless mic capture for macOS.

ffmpeg's own avfoundation input drops audio chunks on some Macs (about 1 in 8 in testing), so the device is
read through CoreAudio (sounddevice) and piped into ffmpeg, which then only ever sees a complete stream.
"""
import queue
import subprocess
import sys
import threading

import sounddevice as sd

RATE = 48000
BUILTIN_HINTS = ("MacBook", "Built-in", "iMac", "Mac mini", "Studio Display")  # the Mac's own microphones


def _inputs():
    return [(i, d) for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]


def _is_builtin(name):
    return any(h.lower() in name.lower() for h in BUILTIN_HINTS)


def find_input(name=""):
    """Pick the input device: the one whose name contains `name` if given and present; otherwise the system
    default input, unless that is an iPhone (Continuity can switch the default to it), then the built-in mic."""
    devices = _inputs()
    if name:
        for i, d in devices:
            if name.lower() in d["name"].lower():
                return i
    default = sd.default.device[0]
    names = dict(devices)
    if default in names and "iphone" not in names[default]["name"].lower():
        return default
    for i, d in devices:
        if _is_builtin(d["name"]):
            return i
    if devices:
        return devices[0][0]
    raise SystemExit("no microphone found")


def input_names():
    """Names of the input devices macOS has right now. Queried in a separate process: PortAudio only
    sees plug/unplug after a re-init, and re-initialising here would kill the stream in use."""
    code = ("import sounddevice as sd;"
            "print('\\n'.join(d['name'] for d in sd.query_devices() if d['max_input_channels'] > 0))")
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=10).stdout
    return [n for n in out.splitlines() if n]


def ffmpeg_from_mic(device_name, ffmpeg_out_args):
    """Start ffmpeg with the mic as mono float32 48 kHz on its input; returns the Popen.

    proc.device is the device name, proc.builtin whether it is the Mac's own mic,
    proc.overflows counts CoreAudio input overflows (should stay 0).
    """
    proc = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-v", "error",
         "-f", "f32le", "-ar", str(RATE), "-ac", "1", "-i", "pipe:0", *ffmpeg_out_args],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    q = queue.Queue()
    proc.overflows = 0

    def callback(indata, frames, t, status):
        if status.input_overflow:
            proc.overflows += 1
        q.put(indata[:, 0].tobytes())

    def writer():
        while True:
            try:
                proc.stdin.write(q.get())
            except (BrokenPipeError, ValueError):
                return

    dev = find_input(device_name)
    proc.device = sd.query_devices(dev)["name"]
    proc.builtin = _is_builtin(proc.device)
    stream = sd.InputStream(device=dev, channels=1, samplerate=RATE, dtype="float32", callback=callback)
    stream.start()
    proc.stream = stream  # keep the stream alive as long as the process
    threading.Thread(target=writer, daemon=True).start()
    return proc
