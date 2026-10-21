"""The fact store (todo/16): what is true in-game, and which facts are paused right now.

content/facts.toml holds every fact the prompts may state, one table per key. Humans own it; tests/test_facts.py
validates every edit, and deploy/check.sh runs the tests before a deploy, so a broken edit never goes live.
data/facts_paused.json holds the fact desk's runtime pauses (scripts/swan_factdesk.py): a fact the news
contradicted, left out of every prompt until a human re-checks it. A pause holds while the fact's `checked` is
older than the pause, so it ends with a commit: scripts/facts_review.py rewords, retires or re-affirms the fact and
stamps `checked`. (The EC2 box can't push, so the pause file is never edited to lift a pause.)

TEXTS and NOTES are the active facts (content.FACTS and content.FACT_NOTES are the same dicts). They are rebuilt in
place whenever the pause file changes: every accessor here calls refresh(), which costs one stat, so the bot picks
up a pause on its next draft without a restart.
"""
import datetime as dt
import json
import os
import pathlib
import re
import time
import tomllib

from . import config

FILE = config.ROOT / "content" / "facts.toml"
# tests/conftest.py points this at a missing file, so a live pause on the box can't change what the tests see
PAUSED_FILE = pathlib.Path(os.environ.get("SWAN_FACTS_PAUSED") or config.DATA / "facts_paused.json")
STATUSES = ("active", "paused")
UTC = dt.timezone.utc


def load(path=FILE):
    """(table, false_claims): every fact in file order, and the patterns of claims that are false in-game."""
    data = tomllib.loads(pathlib.Path(path).read_text())
    return ({k: v for k, v in data.items() if isinstance(v, dict)},
            [p for p in data.get("false_claims", []) if isinstance(p, str)])


def either(patterns):
    """One case-insensitive regex matching any of the patterns, or None for none."""
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.I) if patterns else None


def when(value):
    """A TOML date or datetime, or an ISO string, as an aware UTC datetime (a date is its midnight UTC; a naive
    time is UTC); None if it isn't one."""
    if isinstance(value, str):
        try:
            value = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, dt.date):
        return dt.datetime(value.year, value.month, value.day, tzinfo=UTC)
    return None


TABLE, FALSE_CLAIM_PATTERNS = load()
FALSE_CLAIMS = either(FALSE_CLAIM_PATTERNS)
SAYS = {k: either(f["says"]) for k, f in TABLE.items() if f.get("says")}
TEXTS, NOTES = {}, {}       # the active facts: key -> text / note
PAUSED = {}                 # key -> why it is out of the prompts: "file" (its status) or the runtime pause record
changed_at = 0.0            # when a refresh last paused something new (drafts pooled before it are dropped)
_UNREAD = object()
_stamp = _UNREAD


def linked(frame_key):
    """Facts whose `frames` list names this frame (they join the frame's own list in content.py)."""
    return [k for k, f in TABLE.items() if frame_key in (f.get("frames") or [])]


def read_pauses(path=None):
    """The runtime pause records {fact: {since, slug, quote, ...}}: {} without a file, ValueError if unreadable."""
    try:
        data = json.loads(pathlib.Path(path or PAUSED_FILE).read_text())
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        raise ValueError(f"not JSON: {e}") from None
    if not isinstance(data, dict) or not all(isinstance(v, dict) for v in data.values()):
        raise ValueError("not a {fact: record} object")
    return data


def holds(key, rec, table=None):
    """True while a runtime pause holds: the fact exists and wasn't re-checked after the pause. A pause without a
    readable `since` holds until it is removed."""
    table = TABLE if table is None else table
    if key not in table:
        return False
    since = when(rec.get("since")) or dt.datetime.max.replace(tzinfo=UTC)
    checked = when(table[key].get("checked")) or dt.datetime.min.replace(tzinfo=UTC)
    return checked < since


def refresh(force=False):
    """Re-read the pause file if it changed (or force) and rebuild TEXTS, NOTES and PAUSED in place. True if it was
    re-read. An unreadable file keeps the last pauses (and is an error at first load: deploy/check.sh then fails)."""
    global _stamp, changed_at
    try:
        st = PAUSED_FILE.stat()
        stamp = (st.st_mtime_ns, st.st_size, st.st_ino)
    except FileNotFoundError:
        stamp = None
    if stamp == _stamp and not force:
        return False
    try:
        runtime = read_pauses() if stamp else {}
    except (OSError, ValueError) as e:
        if _stamp is _UNREAD:
            raise RuntimeError(f"{PAUSED_FILE} is unreadable ({e}): fix it or delete it") from None
        print(f"facts: {PAUSED_FILE} unreadable ({e}); keeping the last pauses")
        _stamp = stamp
        return False
    _stamp = stamp
    paused = {k: "file" for k, f in TABLE.items() if f.get("status") != "active"}
    paused.update({k: rec for k, rec in runtime.items() if k not in paused and holds(k, rec)})
    if set(paused) - set(PAUSED):
        changed_at = time.time()
    PAUSED.clear()
    PAUSED.update(paused)
    TEXTS.clear()
    TEXTS.update({k: f["text"] for k, f in TABLE.items() if k not in paused})
    NOTES.clear()
    NOTES.update({k: f["note"] for k, f in TABLE.items() if k not in paused})
    return True


def ok(keys):
    """True if every fact in keys is active (an unknown key counts as paused)."""
    refresh()
    return all(k in TEXTS for k in keys)


def active(keys):
    """The keys that are active, in order."""
    refresh()
    return [k for k in keys if k in TEXTS]


def paused_in(text):
    """The first paused fact whose `says` wording the text uses, or None."""
    refresh()
    return next((k for k in PAUSED if k in SAYS and SAYS[k].search(text or "")), None)


def pauses():
    """{fact: record} of the runtime pauses that hold now (file-paused facts left out)."""
    refresh()
    return {k: v for k, v in PAUSED.items() if isinstance(v, dict)}


refresh()
