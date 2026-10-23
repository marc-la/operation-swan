"""Read an append-only jsonl log one line at a time, from a saved place. Never loads the file.

logs/swan_actions.jsonl was 118 MB and 656k lines on 23 Oct (~40 MB a day) while the bot appends to it, and two timer jobs
read it whole with read_text().splitlines(): 394 and 514 MB resident each, OOM-killed on the 913 MB box (todo/34). So:

    for rec in jsonl.Reader(path, contains='"live"'):          # every dict line holding the text, parsed lazily
        ...
    r = jsonl.Reader(path, resume=saved)                       # only what was appended since the last run
    for rec in r: ...
    saved = r.cursor                                           # {"offset", "inode", "head"}: json-able, keep it

Only COMPLETE lines (ending in "\\n") are consumed: the bot appends while we read, so a last line without its newline may
be half written, and the offset stays before it until the rest arrives. Blank, bad-JSON and non-object lines are skipped
(a line cut short by a crash), but still count as consumed. A cursor that no longer fits the file (it is smaller, or has
another inode, or does not start with the bytes it started with: rotated, truncated, copytruncate) is dropped and the
read starts at 0; r.reset says so.
"""
import hashlib
import json
import os
import pathlib

HEAD_BYTES = 256            # the file's first bytes, hashed into the cursor: a replaced file that kept its inode differs here


class Reader:
    """Iterate the dict records of a jsonl file. contains: a substring a line must hold to be parsed at all (a cheap
    filter; only safe when every wanted record is certain to hold it). resume: a cursor from an earlier run, or None.
    After the iteration (or part of it) offset is the byte after the last complete line consumed."""

    def __init__(self, path, resume=None, contains=None):
        self.path = pathlib.Path(path)
        self.contains = contains.encode() if isinstance(contains, str) else contains
        self.resume = resume or None
        self.offset, self.inode, self.head, self.reset = 0, None, _digest(b""), False

    @property
    def cursor(self):
        return {"offset": self.offset, "inode": self.inode, "head": self.head}

    def __iter__(self):
        try:
            f = open(self.path, "rb")
        except FileNotFoundError:
            self.reset = self.resume is not None
            return
        with f:
            st = os.fstat(f.fileno())
            self.inode = st.st_ino
            self.offset = self._start(f, st)
            self.head = self._head(f)
            try:
                f.seek(self.offset)
                for line in f:
                    if not line.endswith(b"\n"):
                        break                                       # being written: leave it for the next read
                    self.offset += len(line)
                    if self.contains and self.contains not in line:
                        continue
                    try:
                        rec = json.loads(line)
                    except ValueError:                              # bad JSON, or bytes that are not UTF-8
                        continue
                    if isinstance(rec, dict):
                        yield rec
            finally:
                self.head = self._head(f)

    def _start(self, f, st):
        """Where to read from: the cursor's offset if it still describes this file, else 0."""
        c = self.resume
        if not c:
            return 0
        n = c.get("offset") or 0
        if c.get("inode") == st.st_ino and 0 <= n <= st.st_size and c.get("head") == self._head(f, n):
            return n
        self.reset = True
        return 0

    def _head(self, f, upto=None):
        """Digest of the file's first bytes (at most HEAD_BYTES, and not past the offset the cursor stands at)."""
        n = min(HEAD_BYTES, self.offset if upto is None else upto)
        f.seek(0)
        return _digest(f.read(n))


def _digest(b):
    return hashlib.sha1(b).hexdigest()[:16]
