#!/usr/bin/env python3
"""Turn a Claude reply (markdown) into speakable text: stdin -> stdout.

Drops what sounds bad read aloud: code blocks, tables, inline code, URLs, file paths,
markdown symbols. Keeps the prose. Caps the length so a long report reads as a summary."""
import re, sys

MAX_CHARS = 1500

t = sys.stdin.read()
t = re.sub(r"```.*?```", " ", t, flags=re.S)                          # code blocks
t = "\n".join(l for l in t.splitlines() if not l.lstrip().startswith("|"))  # tables
t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)                         # [text](url) -> text
t = re.sub(r"https?://\S+", " ", t)                                     # bare urls
t = re.sub(r"`/(\w+)`", r"\1", t)                                       # `/talk` -> talk
t = re.sub(r"`[^`]*[/~][^`]*`", " ", t)                                 # `paths` and `~/x`
t = re.sub(r"`([^`]*)`", r"\1", t)                                      # other inline code: keep words
t = re.sub(r"(?<!\w)~?/[\w.\-]+/[\w./\-]*", " ", t)                     # bare paths (two+ segments)
t = re.sub(r"(?<!\w)~/[\w./\-]*", " ", t)
t = re.sub(r"^\s*#+\s*", "", t, flags=re.M)                             # headings
t = re.sub(r"^\s*[-*]\s+", "", t, flags=re.M)                           # bullets
t = re.sub(r"^\s*\d+\.\s+", "", t, flags=re.M)                          # numbered lists
t = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", t)                     # bold / italics
t = re.sub(r"^Sources?:.*$", "", t, flags=re.M | re.I)                  # source lists
t = t.replace("—", ", ").replace("–", " to ").replace("&", " and ")
t = re.sub(r"[ \t]+", " ", t)
t = re.sub(r"\n{2,}", "\n", t).strip()

if len(t) > MAX_CHARS:
    cut = t[:MAX_CHARS]
    end = max(cut.rfind(". "), cut.rfind("\n"))
    t = (cut[: end + 1] if end > 200 else cut) + " The rest is on screen."
print(t)
