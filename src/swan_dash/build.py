"""Build the team dashboard (todo/09): one static HTML page from the bot's own files. swan-dash.timer runs it every
minute on EC2 and nginx serves the result behind a password.

    python -m swan_dash.build --out /var/www/swan        # (from src/) what the timer runs
    python -m swan_dash.build --out /tmp/swan            # local preview from this checkout's logs/ and data/

It reads logs/ and data/ only. It never opens .env or secrets/ (the systemd unit also makes them inaccessible) and
needs no network. Every value on the page is picked field by field; whole records are never rendered.
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import tomllib
from zoneinfo import ZoneInfo

import jinja2

from swan_blue.evidence import awards_by_rate, first_later
from swan_bot import config as bot_config  # constants only (FACTDESK_AUTO): it reads no .env on import

ROOT = pathlib.Path(__file__).resolve().parents[2]
PERTH = ZoneInfo("Australia/Perth")
SYDNEY = ZoneInfo("Australia/Sydney")          # competition days roll over at midnight Sydney (9pm Perth)
QUOTA_DAY = ZoneInfo("America/Los_Angeles")    # data/llm_usage.json days (swan_bot/llm.py): free quotas reset there
TEAM_CAP_PER_MIN = 3                           # posts + replies + reposts, team-wide (rules)
LIVE_CAP, TOTAL_CAP = 50, 200                  # accounts alive at once / ever
WRITES = {"post": "post", "reply": "1st reply", "second_voice": "2nd voice", "reply_back": "2nd reply",
          "journalist": "journalist", "thread": "own thread", "thread_answer": "thread answer", "repost": "repost"}
STATUS_WORD = {"green": "RUNNING", "amber": "ALERT", "red": "DOWN"}   # browser tab title (a colour word clashes with the Red track)
# poll awards and Red multiplier changes, as Sydney calendar dates (docs/01-competition/schedule.md)
POLLS = [(dt.date(2026, 10, 21), "Poll 1", 1), (dt.date(2026, 10, 25), "Poll 2", 7000),   # 7,000 since 20 Oct
         (dt.date(2026, 10, 29), "Poll 3", 7000)]
MULTIPLIERS = [(dt.date(2026, 10, 26), 2), (dt.date(2026, 11, 1), 4)]     # derived, not confirmed by organisers
LOG_TAIL_BYTES = 6_000_000                     # likes are logged one per line; this covers several hours
STALE_STATUS_S = 300
DEGRADED_FROM = 5                              # index in the LLM chain: the 6th model or lower is degraded (Marc, 22 Oct)
STALL_S = 5 * 60                               # every LLM parked this long or longer: red
PORTAL_STALE_S = 45 * 60                       # swan-portal.timer runs every 15 min
PULSE_MAX_AGE_S = 2 * 3600                     # swan_bot config.PULSE_MAX_AGE_S: older, the bot doesn't use it
ACTIVITY_TOP, ACTIVITY_ALL = 12, 60          # rows always shown / rows behind "Older activity"
LONG_PARK_S = 600                              # per-minute parks are noise; longer ones go in the activity log
THREAD_SHOWN = 3                               # replies in a thread shown before "… N more"
REJECT_WINDOW_S = 15 * 60                      # old records (no draft_id): rejects this soon before a write are its own
CHILDREN = {"thread", "thread_answer", "repost"}            # writes that belong to an amplified post (amp_post)
SOURCES = {"latest": "Latest", "trending": "Trending", "thread": "a thread", "news": "a news story"}
# the decisions logged on each write, in plain words, and where to change them (src/swan_bot/)
KNOBS = [("frame", "frame", "content.FRAMES"), ("lever", "lever", "content.LEVERS"),
         ("shape", "shape", "content.HOOKS"), ("hook", "hook", "content.HOOKS"),
         ("style", "thread style", "content.THREAD_STYLES"), ("opener", "opener", "content.OPENERS"),
         ("storyline", "storyline", "content.STORYLINES"), ("voice", "voice", "playbook/voices.py"),
         ("reply_mode", "reply mode", "experiment.REPLY_MODES"), ("ask_kind", "ask", "experiment.ASK_KINDS"),
         ("length_band", "length", "experiment.LENGTH_BANDS"), ("close", "close", "experiment.CLOSES"),
         ("backend", "model", "llm.py")]
FLAGS = [("concede", "concedes first"), ("rebuttal", "answers a Yes reason"), ("pulse_news", "pulse news hook")]
HOMES = [("persona, persona today", "content.PERSONAS"), ("typos (hand)", "humanize.HANDS"),
         ("rejects", "quality.py"), ("amplification levels", "config.AMP_LEVELS")]


def read_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def tail_jsonl(path, nbytes=LOG_TAIL_BYTES):
    """Records from the last nbytes of a jsonl file, oldest first (a cut first line is skipped)."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - nbytes))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except FileNotFoundError:
        return []
    if size > nbytes:
        lines = lines[1:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def tail_lines(path, n=50):
    try:
        return path.read_text().splitlines()[-n:]
    except FileNotFoundError:
        return []


def ts(s):
    """ISO time ('...Z' or '+00:00') -> aware datetime, or None."""
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def service_state():
    """'active', 'inactive', 'failed', ... or None where systemd isn't there (a laptop preview)."""
    try:
        r = subprocess.run(["systemctl", "is-active", "swan-bot"], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def ago(delta):
    s = int(delta.total_seconds())
    if s < 90:
        return "just now" if s < 45 else "1 min ago"
    if s < 5400:
        return f"{s // 60} min ago"
    if s < 48 * 3600:
        return f"{s // 3600} h ago"
    return f"{s // 86400} days ago"


def until(delta):
    s = max(0, int(delta.total_seconds()))
    d, h, m = s // 86400, s % 86400 // 3600, s % 3600 // 60
    return f"{d}d {h}h" if d else f"{h}h {m}m" if h else f"{m}m"


def perth(t):
    return t.astimezone(PERTH)


def hm(t):
    return perth(t).strftime("%H:%M")


def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def short(text, n=110):
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def sydney_midnight(day):
    return dt.datetime.combine(day, dt.time(), SYDNEY)


def bundle(rows):
    """Runs of back-to-back ops rows (LLM parks and deploys: each deploy restarts the bot, which re-parks the models)
    become one row that opens to show them. rows are newest first; so is each bundle."""
    items = []
    for r in rows:
        last = items[-1] if items else None
        if r.get("family") and last and last.get("family") == r["family"]:
            if last["kind"] != "group":
                last = items[-1] = dict(kind="group", family=r["family"], t=last["t"], time=last["time"],
                                        who="", post=None, rows=[last])
            last["rows"].append(r)
        else:
            items.append(r)
    for g in items:
        if g["kind"] != "group":
            continue
        g["id"] = f"g-{g['family']}-{int(g['t'].timestamp())}"
        parks = [r for r in g["rows"] if r.get("model")]
        deploys = [r for r in g["rows"] if not r.get("model")]
        g["what"] = f"{'LLM parked' if not deploys else 'deploys' if not parks else 'ops'} ×{len(g['rows'])}"
        parts = [f"{len(deploys)} deploy{'s' if len(deploys) > 1 else ''} (latest {deploys[0]['text']})"] if deploys else []
        newest = {}                             # newest park per model, models with the same reason together
        for r in parks:
            newest.setdefault(r["model"], r)
        by_reason = {}
        for r in newest.values():
            by_reason.setdefault(f"{r['why']} until {r['until']}", []).append(r["model"])
        parts += [f"{', '.join(ms)}: {why}" for why, ms in by_reason.items()]
        g["text"] = short(" · ".join(parts), 220)
    return items


def plain(v):
    """A logged key in words: 'F10_staff_and_livelihoods' -> 'staff and livelihoods (F10)', 'reason_first' -> ..."""
    m = re.match(r"F(\d+)_(.+)", str(v))
    return f"{m[2].replace('_', ' ')} ({'F' + m[1]})" if m else str(v).replace("_", " ")


def theirs(text):
    """Someone else's post as plain text: escaped by Jinja, and links shown as [link], never clickable."""
    return re.sub(r"https?://\S+", "[link]", " ".join((text or "").split()))


def write_item(a):
    """One write, field by field: the text, why it was written that way, what it answered."""
    full = " ".join((a.get("text") or "").split())
    w = dict(t=a["_t"], time=hm(a["_t"]), who=a.get("persona") or a.get("username"), what=WRITES[a["act"]],
             act=a["act"], post=a.get("post_id"), text=short(full), full=full, owner=a.get("owner"),
             why=[(label, plain(a[k])) for k, label, _ in KNOBS if a.get(k) not in (None, "", "none")]
             + [(label, "yes") for k, label in FLAGS if a.get(k) is True],
             now=a.get("now"), hand=", ".join(a.get("hand") or []), clean=a.get("clean"),
             rejects=[], answers=[], children=[], last=a["_t"], target=None, parent=None,
             reposts=[], likes=None, plan=None, measures=[], summary="", latest=None, shown=[], more=[])
    if a.get("target_post") and a["act"] != "repost":
        lean = " · ".join(plain(x) for x in (a.get("target_stance"), a.get("target_class")) if x)
        w["target"] = dict(post=a["target_post"], author=a.get("target_author"), text=theirs(a.get("target_text")),
                           lean=lean, source=SOURCES.get(a.get("source"), a.get("source")),
                           context=theirs(a.get("context")) or None)
    if a.get("parent_text"):                    # a reply-back: our message they answered
        w["parent"] = dict(post=a.get("parent_post"), text=" ".join(a["parent_text"].split()))
    return w


def post_texts(actions, data):
    """{post id: (author, text)} for posts we can name without a read: our own writes, what our replies answered,
    and the bot's latest feed snapshot (data/latest_snapshot.json)."""
    out = {}
    for p in (read_json(data / "latest_snapshot.json") or {}).get("posts") or []:
        if isinstance(p, dict) and p.get("post_id") and p.get("body"):
            out[str(p["post_id"])] = (f"account {p.get('author_id')}", p["body"])
    for a in actions:
        if a.get("target_post") and a.get("target_text"):
            out[str(a["target_post"])] = (f"account {a.get('target_author')}", a["target_text"])
        if a.get("post_id") and a.get("text") and a.get("act") in WRITES:
            out[str(a["post_id"])] = (f"@{a.get('username')}", a["text"])
    return out


def conversations(actions, texts=None):
    """Our live writes as conversations, rows newest activity first. An amplified post carries its thread, reposts,
    likes, plan and measurements; a reply carries its second voice; a reply-back sits under the message of ours it
    answers when that is in the log. Rejected drafts sit under the write they preceded."""
    ours = {a["account_id"] for a in actions if a.get("account_id") and a.get("act") in (*WRITES, "register")}
    writes, tops, rows = {}, {}, []           # post id -> its write / the row it is shown in
    pending = {}                                # (persona, mode) -> rejects since that voice's last write in that mode
    by_draft = {}
    for a in actions:
        act = a.get("act")
        if act == "reject":
            r = dict(t=a["_t"], why=plain(a.get("why") or "?").strip(" ,"), raw=short(a.get("raw"), 200))
            if a.get("draft_id"):
                by_draft.setdefault(a["draft_id"], []).append(r)
            else:
                pending.setdefault((a.get("persona"), a.get("mode")), []).append(r)
            continue
        if act not in WRITES or a.get("live") is not True:
            continue
        w = write_item(a)
        if act == "repost" and not w["full"]:          # a bare repost row said nothing (Marc): what was reposted
            who, body = (texts or {}).get(str(a.get("target_post")), (f"account {a.get('target_author')}", ""))
            w["full"] = w["text"] = (f"reposted #{a.get('target_post')} by {who}: “{short(theirs(body), 80)}”"
                                     if body else f"reposted #{a.get('target_post')} by {who} (text not in our logs)")
        if a.get("draft_id"):
            w["rejects"] = by_draft.pop(a["draft_id"], [])
        else:
            w["rejects"] = [r for r in pending.pop((a.get("persona"), act), [])
                            if (a["_t"] - r["t"]).total_seconds() <= REJECT_WINDOW_S]
        if w.get("target"):
            w["target"]["ours"] = w["target"]["author"] in ours
        parent = None
        if act in CHILDREN and a.get("amp_post") in writes:
            parent = writes[a["amp_post"]]
        elif act == "second_voice":
            parent = next((r for r in reversed(rows) if r["act"] == "reply" and r.get("target")
                           and r["target"]["post"] == a.get("target_post")), None)
        elif act == "reply_back" and a.get("parent_post") in writes:
            parent = writes[a["parent_post"]]
        if parent is None:
            rows.append(w)
        elif act == "repost":
            parent["reposts"].append(w["who"])
        elif act == "thread_answer":               # under the reply it answers, else at the end of the thread
            q = next((c for c in parent["children"] if c["post"] == a.get("target_post")), None)
            (q["answers"] if q else parent["children"]).append(w)
        elif act == "reply_back" and parent["act"] != "post":
            parent["answers"].append(w)
        else:
            parent["children"].append(w)
        top = w if parent is None else tops.get(parent["post"], parent)
        top["last"] = a["_t"]
        if w["post"]:
            writes[w["post"]], tops[w["post"]] = w, top
    amp = {r["post"]: r for r in rows if r["act"] == "post" and r["post"]}
    likes = {}
    for a in actions:
        pid = a.get("post_id")
        if a.get("act") == "like" and a.get("live") and pid in amp:
            likes[pid] = likes.get(pid, 0) + 1
        elif a.get("act") == "amp_plan" and pid in amp:
            amp[pid]["plan"] = dict(level=a.get("level"), likes=a.get("likes"), replies=len(a.get("replies") or []),
                                    reposts=a.get("reposts"))
        elif a.get("act") == "amp_measure" and pid in amp:
            m = dict(at=f"+{a.get('at_h', 0):g} h", gone=a.get("hidden_or_gone"),
                     citizen_likes=a.get("citizen_likes"), citizen_replies=a.get("citizen_replies"),
                     views=None if a.get("views") is None else a["views"] - (a.get("own_views") or 0),
                     rank=a.get("best_rank"))
            amp[pid]["measures"].append(m)
            amp[pid]["last"] = max(amp[pid]["last"], a["_t"])
    for r in rows:
        if r["post"] in likes:
            r["likes"] = likes[r["post"]]
        n = len(r["children"])
        r["shown"], r["more"] = r["children"][:THREAD_SHOWN], r["children"][THREAD_SHOWN:]
        r["kind"] = "write"
        r["id"] = f"w{r['post'] or int(r['t'].timestamp())}"
        r["latest"] = hm(r["last"]) if r["last"] > r["t"] else None
        bits = [r["plan"]["level"]] if r["plan"] else []
        if r["act"] == "post" and (n or r["likes"] or r["reposts"]):
            bits.append(f"{r['likes'] or 0}♥ {n}↩ {len(r['reposts'])}⟲")
        if r["measures"]:
            m = r["measures"][-1]
            bits.append(f"{m['at']}: hidden or gone" if m["gone"] else
                        f"{m['at']}: {m['citizen_likes'] or 0} citizen ♥, {m['citizen_replies'] or 0} ↩")
        answered = [x for x in r["answers"] + r["children"] if x["act"] == "reply_back"]
        if r["act"] != "post" and answered:
            bits.append("they answered")
        r["summary"] = " · ".join(bits)
    return rows


# ---- Score & targets: the portal's points log, split by kind (todo/29) ----
# The portal logs one total an hour for a mix of things ("34 likes, 36 replies, 1 first inauthentic report ..."). Each
# part is weighed by the scoring guide's base value (docs/03-scoring/scoring-cheatsheet.md; a pool share as a small
# value) and the hour's real total is shared out in proportion: the totals are the portal's, a mixed hour's split is
# ours (shown with ≈).
POINT_KINDS = [("persuasion", "Persuasion"), ("engagement", "Views & engagement"), ("blue", "Blue awards"),
               ("polls", "Polls"), ("penalties", "Penalties")]
POINT_LINES = 4                                # the last few portal lines shown under each kind
PART = re.compile(r"(\d+) (.*)")
MIND_SIDES = {"toward No": (160, 8), "away from No": (-80, -2), "neither side": (20, 1), "other view": (20, 1)}


def _part(what):
    """(kind, label, base points a unit) for one part of a portal message, e.g. 'likes' or 'contributions to
    changes of mind on vaccination towards neither side'."""
    w = what.lower()
    if "mind" in w:
        share = "contribution" in w and "primary" not in w
        side = ("toward No" if "towards your side" in w else "away from No" if "away from your side" in w
                else "neither side" if "neither side" in w else "other view")
        return ("penalties" if side == "away from No" else "persuasion",
                f"{side} ({'contribution' if share else 'primary'})", MIND_SIDES[side][1 if share else 0])
    if "report" in w:
        label, base = (("first reporter", 25) if "first" in w else ("account upheld", 15) if "account" in w
                       else ("later reporter", 5))
        return "blue", label, base
    if "unfollow" in w:
        return "penalties", "unfollows", -20
    for stem, label, base in (("view", "views", 1), ("like", "likes", 5), ("repost", "reposts", 10),
                              ("repl", "replies", 15), ("follow", "follows", 20)):
        if stem in w:
            return "engagement", label, base
    return "engagement", short(w, 40), 1


def score_lines(points, since):
    """Points since `since` by kind, each with the counts behind it and its last portal lines (newest first). Kinds
    with nothing are left out."""
    out = {k: dict(kind=k, name=name, points=0.0, counts={}, lines=[], events=0, mixed=False)
           for k, name in POINT_KINDS}
    for e in sorted((e for e in points if e["_t"] >= since), key=lambda e: e["_t"], reverse=True):
        msg = e.get("message") or ""
        head, _, rest = msg.partition(": ")
        est, counts = {}, {}
        if head.startswith("Narrative"):           # a poll award: "Narrative: the poll was too close to call ..."
            est["polls"] = e["points"]
        else:
            for part in re.split(r",| and ", rest):
                m = PART.match(part.strip())
                if m:
                    kind, label, base = _part(m.group(2))
                    est[kind] = est.get(kind, 0) + int(m.group(1)) * base
                    counts.setdefault(kind, {})[label] = counts.get(kind, {}).get(label, 0) + int(m.group(1))
        if not est:
            est["penalties" if e["points"] < 0 else "engagement"] = e["points"]
        share, pts = {}, e["points"]
        if "blue" in est and len(est) > 1:         # a combined line: Blue by its counts (Marc, 22 Oct), the rest is
            rate = float(RATE.search(head).group(1)) if RATE.search(head) else 1.0      # engagement/persuasion
            share["blue"] = max(0.0, min(est.pop("blue") * rate, pts)) if pts > 0 else 0.0
            pts -= share["blue"]
        total = sum(est.values())
        if len(est) == 1:
            share.update({k: pts for k in est})
        elif total and pts / total > 0:
            share.update({k: v * pts / total for k, v in est.items()})
        else:                                      # signs disagree: our weights, the rest on the largest kind
            big = max(est, key=lambda k: abs(est[k]))
            share.update(est)
            share[big] += pts - total
        est = share                                # len(est) > 1 below: a split line (≈)
        for k, v in share.items():
            o = out[k]
            o["points"] += v
            o["events"] += 1
            o["mixed"] |= len(est) > 1
            for label, n in counts.get(k, {}).items():
                o["counts"][label] = o["counts"].get(label, 0) + n
            if len(o["lines"]) < POINT_LINES:        # this kind's part of the hour only, not the whole message
                o["lines"].append(dict(time=hm(e["_t"]), points=round(v), of=e["points"] if len(est) > 1 else None,
                                       text=" · ".join(f"{n:,} {label}" for label, n in counts.get(k, {}).items())
                                       or short(rest or msg, 160)))
    rows = [dict(o, points=round(o["points"]), counts=sorted(o["counts"].items(), key=lambda kv: -kv[1]))
            for o in out.values() if o["events"]]
    have = {r["kind"]: r for r in rows}
    tiles = [have.get(k) or dict(kind=k, name=name, points=0, mixed=False) for k, name in POINT_KINDS
             if k != "polls" or k in have]
    return dict(rows=rows, tiles=tiles, total=sum(e["points"] for e in points if e["_t"] >= since))


# the activity log's alert kinds, each its own colour (Marc, 22 Oct): message prefix -> (label, css class on the row)
ALERT_KINDS = [(r"DEPLOY FAILED", "deploy failed", "deployfail"), (r"BLUE", "Blue", "blue"),
               (r"(BOT|SERVICE) (CRASHED|DOWN|OFFLINE)", "service down", "bad"), (r".*suspend", "suspended", "susp")]


# ---- the fact desk (todo/16): pauses and open proposals, with the command that settles each ----
REVIEW = "python scripts/facts_review.py"
KINDS = {"contradiction": "contradicts", "reword": "rewording", "new_fact": "new fact", "angle": "idea"}
HINTS = {
    "contradiction": "Does the paper report this as fact? Yes: accept (the new wording gets a new key; what was written "
                     "for the old one stays out until someone rewrites it). Only the wording or timing was off: "
                     "same key. The paper slipped: reject (the fact comes back as it is).",
    "reword": "Still true, said better or more currently. Accept if the new wording is accurate and no weaker.",
    "new_fact": "Accept only if it is true in the setting and useful to No, or something Yes will use that we must "
                "not contradict. Its figures become allowed in drafts.",
    "angle": "An argument idea for the writers; accepting files it in frames-and-messengers (no prompt changes).",
}


def _when(v):
    """A TOML date / date-time or an ISO string as an aware UTC datetime (a date is its midnight), else None."""
    if isinstance(v, str):
        return ts(v)
    if isinstance(v, dt.datetime):
        return v if v.tzinfo else v.replace(tzinfo=dt.timezone.utc)
    if isinstance(v, dt.date):
        return dt.datetime(v.year, v.month, v.day, tzinfo=dt.timezone.utc)
    return None


MIN_T = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
AUTO_SHOWN = 15                                # autopilot decisions listed, newest first
DESK_STALL_S = 150 * 60                        # swan-factdesk.timer runs hourly: no run for this long is a problem
DESK_PROBLEM_S = 24 * 3600                     # a failed facts test stays on the page this long
AUTO_UNDO = "ssh swan-ec2 'cd ctn && .venv/bin/python scripts/facts_review.py --undo {id}'"   # = factdesk.UNDO


def fact_desk(root, now=None):
    """The Facts section (todo/29: the desk on autopilot): its decisions, newest first, each with its undo command;
    pauses that hold (facts.toml and the desk's overlay not re-checked since); and what is left for a human
    (proposals without a committed or auto decision), urgent first, with the review commands. None without the
    files."""
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        table = {k: v for k, v in tomllib.loads((root / "content" / "facts.toml").read_text()).items()
                 if isinstance(v, dict)}
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return None
    try:                                       # the desk's overlay (todo/29), merged as swan_bot/facts.py does
        for k, t in tomllib.loads((root / "data" / "facts_auto.toml").read_text()).items():
            if isinstance(t, dict) and (k not in table or (_when(t.get("checked")) or MIN_T)
                                        >= (_when(table[k].get("checked")) or MIN_T)):
                table[k] = t
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        pass
    pauses = read_json(root / "data" / "facts_paused.json") or {}
    held = {k: v for k, v in pauses.items() if isinstance(v, dict) and k in table
            and (_when(table[k].get("checked")) or MIN_T)
            < (_when(v.get("since")) or dt.datetime.max.replace(tzinfo=dt.timezone.utc))}
    decided = {d.get("id") for d in tail_jsonl(root / "content" / "fact_decisions.jsonl")}
    autolog = tail_jsonl(root / "data" / "facts_auto.jsonl")
    last = {r.get("id"): r for r in autolog}                       # a proposal's latest auto decision
    decided |= {i for i, r in last.items() if r.get("status") not in ("failed", "undone")}
    props = {}
    for r in tail_jsonl(root / "data" / "fact_proposals.jsonl"):
        if "kind" in r and r.get("kind") in KINDS:
            props[r["id"]] = r
    undone = {r.get("id") for r in autolog if r.get("status") == "undone"}
    today = sydney_midnight(now.astimezone(SYDNEY).date())
    log = []
    for r in reversed(autolog):
        t = ts(r.get("decided_at"))
        if not t or len(log) >= AUTO_SHOWN or r.get("status") not in ("accepted", "retired"):
            continue                              # the list is what went live; failures wait for a human
        p = props.get(r.get("id"), {})
        fact = r.get("fact") or p.get("fact") or p.get("key")
        text = (r.get("text") or p.get("text")) if r.get("status") == "accepted" else \
            f"Retired: {table.get(fact, {}).get('text') or fact}"
        log.append(dict(
            id=r.get("id"), date=perth(t).strftime("%-d %b"), status=r.get("status"), text=short(text, 240),
            paper=(r.get("site") or "").replace("-", " ").title(),
            url=f"https://sites.legitreal.com/{r.get('site')}/articles/{r.get('slug')}" if r.get("site") else None,
            reverted=r.get("id") in undone, undo=AUTO_UNDO.format(id=r.get("id"))))
    # only serious problems are loud (Marc, 22 Oct): a failed facts test, or the desk erroring or stalled
    problems = []
    tested = next((r for r in reversed(autolog) if "tests/test_facts.py failed" in (r.get("summary") or "")), None)
    if tested and (now - (ts(tested.get("decided_at")) or MIN_T)).total_seconds() < DESK_PROBLEM_S:
        problems.append(f"tests/test_facts.py failed with the desk's changes at {hm(ts(tested['decided_at']))}: "
                        f"none of them went live")
    state_file = root / "data" / "factdesk_state.json"
    last_run = ts((read_json(state_file) or {}).get("last_run"))
    if last_run is None and state_file.exists():
        last_run = dt.datetime.fromtimestamp(state_file.stat().st_mtime, dt.timezone.utc)
    if bot_config.FACTDESK_AUTO and last_run and (now - last_run).total_seconds() > DESK_STALL_S:
        problems.append(f"the fact desk hasn't run since {hm(last_run)} "
                        f"(on the box: journalctl -u swan-factdesk -n 50)")
    auto = dict(on=bot_config.FACTDESK_AUTO, cap=bot_config.FACTDESK_AUTO_PER_DAY, log=log, problems=problems,
                today=sum(1 for r in autolog if r.get("status") in ("accepted", "retired")
                          and (ts(r.get("decided_at")) or MIN_T) >= today))
    items = []
    for p in props.values():
        if p["id"] in decided:
            continue
        fact = p.get("fact")
        paused = fact in held and held[fact].get("proposal") == p["id"]
        cmd, pid = f"{REVIEW} --accept {p['id']}", p["id"]
        if p["kind"] == "contradiction":
            commands = ([cmd, f"{cmd} --same-key"] if p.get("text") else
                        [f'{cmd} --text "…" --note "…"', f'{cmd} --same-key --text "…" --note "…"'])
            commands.append(f"{REVIEW} --reject {pid}")
        else:
            commands = [cmd, f"{REVIEW} --reject {pid}"]
        items.append(dict(
            id=pid, kind=p["kind"], label=KINDS[p["kind"]], paused=paused, name=fact or p.get("key") or "",
            now=table.get(fact, {}).get("text") if fact else None, new=p.get("text") or p.get("idea"),
            note=p.get("note"), failed=p.get("failed_checks"), quote=short(p.get("quote"), 400),
            paper=(p.get("site") or "").replace("-", " ").title(), opinion=p.get("opinion"),
            url=f"https://sites.legitreal.com/{p.get('site')}/articles/{p.get('slug')}",
            when=(ts(p.get("published_at")) or ts(p.get("ts")) or dt.datetime.now(dt.timezone.utc)).strftime("%-d %b"),
            stated_in=p.get("stated_in") or [], numbers=p.get("new_numbers") or [], also=len(p.get("also") or []),
            hint=HINTS[p["kind"]], commands=commands,
            left=short(last[p["id"]].get("summary"), 200) if p["id"] in last else None))
    order = list(KINDS)
    items.sort(key=lambda i: (not i["paused"], order.index(i["kind"]), -i["id"]))
    rest = [i["id"] for i in items if i["kind"] == "angle"]
    return dict(paused=[dict(fact=k, since=hm(ts(v.get("since"))) if ts(v.get("since")) else "?",
                             proposal=v.get("proposal"), text=short(table[k].get("text"), 200),
                             paper=(v.get("site") or "").replace("-", " ").title()) for k, v in held.items()],
                proposals=items, count=len(items), auto=auto,
                reject_ideas=f"{REVIEW} --reject {','.join(map(str, rest))}" if len(rest) > 1 else None)


# ---- Blue (todo/07, src/swan_blue): only what the team needs to decide ----
BLUE_STALE_S = 10 * 60                         # swan-blue writes its status every minute
# Red is down: back to the commit before the running one. swan-update.timer would pull origin/main again within 2 min,
# so it is paused first; start it again once a fix is pushed.
ROLLBACK = ("ssh swan-ec2 'cd ctn && sudo systemctl stop swan-update.timer && git reset --hard {prev} && "
            "sudo systemctl restart swan-bot swan-blue swan-lab'")
BLUE_APPROVE = "ssh swan-ec2 'ctn/scripts/blue.sh approve all'"
BLUE_ERROR_S = 2 * 3600                        # an older error has been dealt with or retried: not shown
# Is Blue going well? A day's Blue points against the modelled ceiling (docs/06-strategy/blue-reporting.md §2:
# ~70 reports a day refilled around the clock), and when a day falls short, the first lever below its bar.
BLUE_TARGET_DAY = 1200
BLUE_GOOD, BLUE_POOR = 0.9, 0.6                # share of target: green at or above GOOD, red below POOR
BLUE_BARS = (("filed", 50, "slots: only {v} reports filed (about 70 fit in a day)"),
             ("hit", 0.8, "moderator: only {v:.0%} of rulings hidden (about 90% expected)"),
             ("first", 0.6, "speed: only {v:.0%} paid as first reporter (aim for 80%)"))
BLUE_LOCKED_H = 14                             # more hours locked than this: genuine rulings cost the day
BLUE_PER_AWARD = 20                            # under this per paid award: the per-team daily rates are cutting in
BLUE_MSG = re.compile(r"moderat|inauthentic|suspen", re.I)


# Reports since 9pm (todo/29, Marc 22 Oct): the chronological timeline, one row per report, where each run of
# consecutive rows with the same settled outcome collapses in place into one line that opens to those rows. Pending
# and genuine rows never collapse.
BLUE_CSS = {"hidden": "up", "pending": "warn", "genuine": "down"}       # one colour per outcome; the rest neutral
BLUE_ACCOUNT_PTS = 15                          # an upheld account report (scoring cheatsheet), times the line's ×rate
BATCH_S = 120                                  # portal lines this close together are one hourly scoring run
UPHELD = re.compile(r"(\d+) upheld account reports?", re.I)
RATE = re.compile(r"×\s*([\d.]+) points")


def account_outcomes(ledger, points):
    """{report key: (outcome, note, css)} for our ruled account reports. The API doesn't show them (a suspended account still
    reads as normal), but the portal's hourly scoring run does: "N upheld account reports". The portal names no
    account, so each ruling is matched to the first scoring run after it, and a run's upheld count is shared over the
    rulings it covers: all suspended, all dismissed, or "k of n" when it's split."""
    runs = []                                  # [time, upheld, points per upheld]
    for e in sorted(points, key=lambda e: e["_t"]):
        msg = e.get("message") or ""
        n = sum(int(m) for m in UPHELD.findall(msg))
        rate = float(RATE.search(msg).group(1)) if RATE.search(msg) else 1.0
        if runs and (e["_t"] - runs[-1][0]).total_seconds() <= BATCH_S:
            runs[-1][1] += n
            runs[-1][2] = runs[-1][2] or (BLUE_ACCOUNT_PTS * rate if n else 0)
        else:
            runs.append([e["_t"], n, BLUE_ACCOUNT_PTS * rate if n else 0])
    batches, out = {}, {}
    for r in ledger:
        t = ts(r.get("at"))
        if r.get("kind") != "post" and r.get("status") == "ruled" and t:
            run = next((x for x in runs if x[0] >= t), None)
            if run is None:
                out[r.get("key")] = ("ruled", "outcome not in the portal log yet", "")
            else:
                batches.setdefault(id(run), (run, []))[1].append(r.get("key"))
    for run, keys in batches.values():
        k, n = min(run[1], len(keys)), len(keys)
        word = (("suspended", f"+{run[2]:g}", "up") if k == n else ("dismissed", "no points, no lock", "") if k == 0
                else ("suspended?", f"{k} of these {n} suspended, the portal doesn't say which", ""))
        for key in keys:
            out[key] = word
    return out


def blue_timeline(ledger, points):
    """Today's reports in filing order (and any still pending), as rows and runs. A row: what, group (swan-blue's
    cluster label), out (the outcome word, coloured by css), detail (target · group · time · note). A run: two or more consecutive rows with the same settled outcome (hidden,
    refused, or the same account outcome), shown as one line ("7 hidden, 14:02–15:40") that opens to its rows."""
    outcomes = account_outcomes(ledger, points)
    rows = []
    for r in ledger:
        t = ts(r.get("at"))
        status = r.get("status")
        if status == "refused":
            continue                           # a platform refusal is plumbing, not a result (Marc, 22 Oct)
        what = f"#{r['target']}" if r.get("kind") == "post" else f"account {r['target']}"
        out, note, css = str(status), "", BLUE_CSS.get(status, "")
        if r.get("kind") != "post" and status == "ruled":
            out, note, css = outcomes.get(r.get("key"), ("ruled", "", ""))
        when = ("rules " if status == "pending" else "") + (hm(t) if t else "")
        rows.append(dict(what=what, group=f"group {r.get('team') or '?'}", at=hm(t) if t else "", t=t,
                         status=status, out=out, note=note, css=css, key=f"{out}|{note}",
                         detail=" · ".join(x for x in (what, f"group {r.get('team') or '?'}", when, note) if x)))
    items = []
    for row in rows:
        last = items[-1] if items else None
        if row["status"] not in ("pending", "genuine") and last and last["key"] == row["key"]:
            if last["kind"] != "run":
                last = items[-1] = dict(kind="run", key=row["key"], rows=[last])
            last["rows"].append(row)
        else:
            items.append(dict(row, kind="row"))
    for i, it in enumerate(items):
        if it["kind"] == "run":
            first, n = it["rows"][0], len(it["rows"])
            times = sorted(r["t"] for r in it["rows"] if r["t"])
            span = "" if not times else hm(times[0]) if hm(times[0]) == hm(times[-1]) else \
                f"{hm(times[0])}–{hm(times[-1])}"
            it.update(out=f"{n} {first['out']}", css=first["css"], label=f"{n} {first['out']}, {span}",
                      detail=" · ".join(x for x in (span, first["note"]) if x),
                      id=f"blue-run-{i}-{first['what'].strip('#').replace(' ', '')}")
    return items


def own_reported(ids, logs):
    """(report lines checked, lines against our own accounts) from logs/blue_reports.jsonl: an account report whose
    target, or any report whose author, is one of ours. ids come from swan-blue's status (ids only: the dashboard
    never reads secrets/); None without them."""
    if not ids:
        return None
    ours, n, hits = {int(i) for i in ids if str(i).isdigit()}, 0, 0
    for r in tail_jsonl(logs / "blue_reports.jsonl", 20_000_000):
        if r.get("act") != "report":
            continue
        n += 1
        if r.get("author") in ours or (r.get("kind") != "post" and r.get("target") in ours):
            hits += 1
    return dict(lines=n, hits=hits, accounts=len(ours))


def perth_span(day):
    """A competition (Sydney) day as the Perth hours it covers, e.g. 'Wed 21 9pm → Thu 22 9pm'."""
    start = perth(sydney_midnight(day))
    end = perth(sydney_midnight(day + dt.timedelta(days=1)))
    fmt = lambda t: t.strftime("%a %-d %-I%p").replace("AM", "am").replace("PM", "pm")
    return f"{fmt(start)} → {fmt(end)}"


def blue_days(days, points, now):
    """By Sydney day, newest first: Blue points and first/later awards from the portal log (the ground truth),
    joined with swan-blue's own counts; for each finished day, its share of target and its weakest lever."""
    portal, by_day = {}, {}
    for e in points:
        by_day.setdefault(e["_t"].astimezone(SYDNEY).date().isoformat(), []).append(e)
    for d, es in by_day.items():
        blue = next((r["points"] for r in score_lines(es, min(e["_t"] for e in es))["rows"] if r["kind"] == "blue"), 0)
        msgs = [e.get("message") or "" for e in es if re.search(r"report", e.get("message") or "", re.I)]
        f, later = first_later(msgs)
        full, reduced = awards_by_rate(msgs)
        if blue or f or later:
            portal[d] = dict(points=blue, first=f, later=later, full=full, reduced=reduced)
    today, rows = now.astimezone(SYDNEY).date().isoformat(), []
    for d in sorted(set(days) | set(portal), reverse=True):
        a, p = days.get(d, {}), portal.get(d, {})
        ruled, paid = a.get("hidden", 0) + a.get("genuine", 0), p.get("first", 0) + p.get("later", 0)
        r = dict(day=perth_span(dt.date.fromisoformat(d)), today=d == today, points=p.get("points", 0),
                 filed=a.get("filed", 0), hidden=a.get("hidden", 0), genuine=a.get("genuine", 0),
                 accounts=a.get("accounts", 0), first=p.get("first", 0), paid=paid, locked_h=a.get("locked_h", 0),
                 full=p.get("full", 0), awards=p.get("full", 0) + p.get("reduced", 0), lever=None)
        r["pct"] = round(100 * r["points"] / BLUE_TARGET_DAY)
        r["level"] = "up" if r["pct"] >= 100 * BLUE_GOOD else "warn" if r["pct"] >= 100 * BLUE_POOR else "down"
        if not r["today"] and r["level"] != "up":
            vals = dict(filed=r["filed"], hit=r["hidden"] / ruled if ruled else None, first=r["first"] / paid if paid else None)
            per_award = r["points"] / paid if paid else None
            r["lever"] = next((msg.format(v=vals[k]) for k, bar, msg in BLUE_BARS
                               if vals[k] is not None and vals[k] < bar), None) or \
                (f"locks: {r['locked_h']:g} h locked" if r["locked_h"] > BLUE_LOCKED_H else None) or \
                (f"team spread: {per_award:.0f} points per award against 25 at full rate (report more teams, "
                 f"fewer per team)" if per_award is not None and per_award < BLUE_PER_AWARD else None) or \
                "no single lever is below its bar"
        rows.append(r)
    return rows


def blue_panel(data, now, points, day_start, logs=None):
    """The Blue section: what needs a decision (the reports waiting, grouped by ring), the state in one line, and
    today's results once there are any. None if swan-blue isn't set up."""
    s = read_json(data / "blue_status.json")
    if not s:
        return None
    t = ts(s.get("ts"))
    locked, nxt, err_t = ts(s.get("locked_until")), ts(s.get("next_ruling")), ts(s.get("last_error_ts"))
    today, prec = s.get("today") or {}, s.get("precision") or {}
    pts = next((r["points"] for r in score_lines(points, day_start)["rows"] if r["kind"] == "blue"), 0)
    rings = [dict(post=r.get("post"), why=short(r.get("why"), 160), reports=r.get("reports"))
             for r in s.get("rings") or []]
    waiting = len(s.get("waiting") or [])
    timeline = blue_timeline(s.get("ledger") or [], points)
    own = own_reported(s.get("own_ids"), logs or data.parent / "logs")
    history = blue_days(s.get("days") or {}, points, now)
    last = next((r for r in history if not r["today"]), None)       # the last finished day decides the verdict
    ready = s.get("ready_ok", s.get("ready")) or 0
    lock_why = short(s.get("lock_why") or "reason not recorded", 60)
    bits = ([f"OUR OWN ACCOUNTS REPORTED: {own['hits']}"] if own and own["hits"] else []) + \
        ([f"{waiting} waiting for approval"] if waiting else []) + \
        ([f"locked until {hm(locked)} Perth ({lock_why})", f"{ready} ready"] if locked else []) + \
        ([f"{s['pending']}/{s['cap']} pending" + (f", next ruling {hm(nxt)}" if nxt and not locked else "")]
         if s.get("pending") else []) + \
        ([f"{today.get('hidden', 0)} hidden since 9pm"] if today.get("filed") else []) + \
        ([f"{pts:+,} pts since 9pm"] if pts else [])
    rows_all = [r for it in timeline for r in (it["rows"] if it["kind"] == "run" else [it])]
    kind = lambda r: ("success" if r["out"] in ("hidden", "suspended") else "failed" if r["out"] in ("genuine", "dismissed")
                      else "pending")                    # pending also holds "ruled, outcome not in the portal log yet"
    counts = {k: sum(kind(r) == k for r in rows_all) for k in ("success", "failed", "pending")}
    return dict(
        stale=t is None or (now - t).total_seconds() > BLUE_STALE_S, ago=ago(now - t) if t else "never",
        summary=" · ".join(bits) or "nothing to report right now", why=s.get("why"),
        locked=hm(locked) if locked else None, lock_why=s.get("lock_why"), pending=s.get("pending"), cap=s.get("cap"),
        lock_estimate=s.get("lock_src") == "estimate", ready=ready, ready_accounts=s.get("ready_accounts") or 0,
        pg_max=s.get("pg_max"), pg_check={"n": 0, **(s.get("pg_check") or {})},
        clusters={"today": 0, "full": 0, **(s.get("clusters") or {})},
        next_ruling=hm(nxt) if nxt else None, waiting=waiting, rings=rings,
        teams=len({r.get("team") for r in s.get("rings") or []}),
        ev=round(sum(r.get("ev") or 0 for r in s.get("rings") or [])), approve=BLUE_APPROVE,
        today={k: today.get(k) or 0 for k in ("filed", "hidden", "genuine", "refused", "accounts")},
        queued=s.get("queued") or 0, first={"first": 0, "later": 0, **(s.get("first") or {})}, own=own,
        timeline=timeline, rows=rows_all, counts=counts,
        rate=prec.get("rate"), ruled=prec.get("n"), history=history, last=last, target=BLUE_TARGET_DAY,
        error=s.get("last_error") if err_t and (now - err_t).total_seconds() < BLUE_ERROR_S
        and not str(s.get("last_error")).startswith("report refused") else None)    # refusals are plumbing (Marc, 23 Oct)


# ---- reach: did we answer every citizen we could, fast, and did it convert? (Marc, 2026-10-22) ----
CITIZEN_WRITES = {"reply", "reply_back", "second_voice", "journalist"}
REACH_SPEED_MIN = 3            # a new citizen post answered within this (median)
REACH_BACK_MIN = 1             # a citizen answering us gets our reply within this (median)
VOLUME_WINDOW_MIN = 30         # posting rate is measured over this long, so a stall or a recovery shows within minutes
VOLUME_GREEN, VOLUME_AMBER = 0.7, 0.35     # share of the team's 3 writes a minute: green at or above, red below AMBER
REACH_SHARE = 0.9              # answered / answerable, and drafts passing on the first LLM call
STEALTH_BANS_DAY = TOTAL_CAP / 14             # new bans since 9pm Perth: 0 green, up to the 200-account allowance over 14 days amber, above red (Marc, 23 Oct)
VOICES_MIN = 10                # a guess: fewer writers than this and throughput drops
MIND = re.compile(r"(\d+) (.*)")

# ---- drafting starved: the drafter found no model (23 Oct, 27,800 jobs lost as no_model in 3 h) ----
NOMODEL_SHORT_MIN, NOMODEL_LONG_MIN = 10, 30   # windows for no_model drops and live writes
NOMODEL_WRITES_FLOOR = 1.0                     # writes a minute over the short window: below it, drops make it red (normal ~2.9, 23 Oct starved ~0.4)
BUDGET_LOW_X = 2                               # priced-model budget left under this many times the amplified-post reserve: amber


def drafting_state(actions, data, now):
    """The 'no model' banner: dict(level, text); green (empty text) when all is well or nothing can be read. Budget maths is swan_bot.llm's own; a missing file or import means no budget signal, not a crash."""
    short, long_ = (now - dt.timedelta(minutes=m) for m in (NOMODEL_SHORT_MIN, NOMODEL_LONG_MIN))
    drops = [a["_t"] for a in actions if a.get("act") in ("lost", "requeue") and a["_t"] >= long_
             and str(a.get("why")).split(":")[-1] == "no_model"]              # "no_model" and "expired:no_model"
    d10, d30 = sum(t >= short for t in drops), len(drops)
    wpm = sum(a["_t"] >= short for a in actions if a.get("act") in WRITES and a.get("live") is True) / NOMODEL_SHORT_MIN
    left = None
    held = low = False
    spent = read_json(data / "llm_spend.json")
    if isinstance(spent, dict):
        try:
            from swan_bot import llm
            day = now.astimezone(llm.BUDGET_DAY).date().isoformat()
            left = llm.allowance(day, spent)
            reserve = bot_config.LLM_AMP_RESERVE_SHARE * llm.day_share(day)
            held, low = left <= reserve, left < BUDGET_LOW_X * reserve
        except Exception:                      # no openai on this machine, odd file: show the drops only
            left = None
    gone = left is not None and left <= 0
    if not (d30 or held or low or gone):
        return dict(level="green", text="")
    level = "red" if gone or (d10 and wpm < NOMODEL_WRITES_FLOOR) else "amber"
    why = " · budget spent: paid models off" if gone else " · paid models held back for amplified posts" if held else ""
    head = "NO MODEL" if d30 else "BUDGET SPENT" if gone else "BUDGET LOW"
    text = f"{head} · {d10} drops in {NOMODEL_SHORT_MIN} min, {d30} in {NOMODEL_LONG_MIN} · {wpm:.1f} writes/min"
    return dict(level=level, text=text + (f" · ${left:.2f} left today" if left is not None else "") + why)


def _id_clock(actions):
    """(post id, unix time) of our own live writes: ids rise with time, so a citizen post's id dates it. Reposts are
    left out: their post_id may be the old post that was reposted, which would put the clock hours out."""
    pts = []
    for a in actions:
        try:
            if a.get("live") is True and a.get("act") in WRITES and a.get("act") != "repost" and a.get("post_id") not in (None, "None"):
                pts.append((int(a["post_id"]), a["_t"].timestamp()))
        except (TypeError, ValueError):
            pass
    return sorted(pts)


def _written_at(pid, clock, max_gap=1800):
    """When post `pid` was written, interpolated between our own posts; None outside what we can date, or when our
    nearest posts are more than max_gap seconds apart (the guess would be hours out: "125 min" replies, 23 Oct)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    for (i0, t0), (i1, t1) in zip(clock, clock[1:]):
        if i0 <= pid <= i1 and i1 > i0:
            if t1 - t0 > max_gap:
                return None
            return t0 + (t1 - t0) * (pid - i0) / (i1 - i0)
    return None


STAGES = ("wait", "draft", "hold")


def _stages(a):
    """(wait, draft, hold) minutes of one write from the bot's stage stamps (t_made: the citizen's post, t_pick, t_drafted,
    t_sent), or None when it has none (older rows) or they are out of order."""
    try:
        made, pick, drafted, sent = (float(a[k]) for k in ("t_made", "t_pick", "t_drafted", "t_sent"))
    except (KeyError, TypeError, ValueError):
        return None
    if not made <= pick <= drafted <= sent:
        return None
    return tuple((hi - lo) / 60 for lo, hi in ((made, pick), (pick, drafted), (drafted, sent)))


def stage_line(rows):
    """'wait 1.2 · draft 0.4 · hold 0.8 = 2.4 min (n 7)': the median of each stage; the parts need not add to the
    total, medians do not."""
    if not rows:
        return "no timed writes yet"
    med = [_median([r[i] for r in rows]) for i in range(3)]
    return (" · ".join(f"{n} {m:.1f}" for n, m in zip(STAGES, med)) +
            f" = {_median([sum(r) for r in rows]):.1f} min (n {len(rows)})")


def _median(xs):
    xs = sorted(xs)
    return None if not xs else (xs[len(xs) // 2] if len(xs) % 2 else (xs[len(xs) // 2 - 1] + xs[len(xs) // 2]) / 2)


def _minds(points, since):
    """Changes of mind in the portal's messages since `since`: toward / away / neither, primary or contribution."""
    out = dict(toward=0, away=0, neither=0, primary_toward=0)
    for e in points:
        if e["_t"] < since:
            continue
        for part in re.split(r",| and ", e.get("message") or ""):
            m = MIND.match(part.strip().removeprefix("NPC engagement: "))
            if not m or "mind" not in m.group(2):
                continue
            n, what = int(m.group(1)), m.group(2)
            side = ("toward" if "towards your side" in what else "away" if "away from your side" in what else
                    "neither" if "neither side" in what else None)       # no side named: an "other view" change
            if side is None:
                continue
            out[side] += n
            if side == "toward" and "contribution" not in what:
                out["primary_toward"] += n
    return out


def reach(actions, status, points, now, day_start, notes=None):
    """Three lights, each green/amber/red against its own bar (Marc, 23 Oct: the old "answered of answerable" is true
    by construction and stayed green while nothing was posting): SPEED (how fast citizens get an answer), VOLUME (are we
    posting at the team budget, with enough voices, losing no one) and CONVERSION (do replies move people toward No).
    Each light is its worst row; rows with no figure yet are grey and never turn a light green."""
    hour_ago, recent = now - dt.timedelta(hours=1), now - dt.timedelta(minutes=VOLUME_WINDOW_MIN)
    refreshes = [a for a in actions if a.get("act") == "refresh"]
    funnel = (refreshes[-1].get("funnel") if refreshes else None) or {}
    keys = sorted(funnel)
    f = funnel[keys[-2]] if len(keys) >= 2 else (funnel[keys[-1]] if keys else None)    # the last full hour
    rows = []

    def row(group, name, light, now_, target="", fix=""):
        rows.append(dict(group=group, name=name, light=light, now=now_, target=target, fix=fix))

    # ---- speed ----
    clock = _id_clock(actions)
    fresh, back = [], []
    stages = dict(fresh=[], back=[])
    for a in actions:
        if a.get("live") is not True or a["_t"] < hour_ago or a.get("group") not in (None, "None"):
            continue
        kind = "fresh" if a.get("act") == "reply" and a.get("source") == "latest" else \
            "back" if a.get("act") == "reply_back" else None
        if kind and (st := _stages(a)):
            stages[kind].append(st)
        st = _stages(a)
        w = _written_at(a.get("target_post"), clock) if st is None else None    # the bot's own stamps beat the id guess
        lag = sum(st) if st else (a["_t"].timestamp() - w) / 60 if w is not None else None
        if lag is None or lag < 0:
            continue
        if a.get("act") == "reply" and a.get("source") == "latest":
            fresh.append(lag)
        elif a.get("act") == "reply_back":
            back.append(lag)
    mf, mb = _median(fresh), _median(back)
    graded = lambda v, bar: "grey" if v is None else "green" if v <= bar else "amber" if v <= 3 * bar else "red"
    row("speed", "Reply time, new citizen posts", graded(mf, REACH_SPEED_MIN),
        f"{mf:.1f} min" if mf is not None else "none this hour", f"≤ {REACH_SPEED_MIN} min",
        "Behind the citizen's session: check the LLM line under Bot.")
    row("speed", "Reply time, citizens answering us", graded(mb, REACH_BACK_MIN),
        f"{mb:.1f} min" if mb is not None else "none this hour", f"≤ {REACH_BACK_MIN} min",
        "Reply-backs are slow: check Bot.")
    for kind, name in (("fresh", "1st replies"), ("back", "2nd replies")):
        row("speed", f"Where the time goes, {name}", "grey", stage_line(stages[kind]), "wait + draft + hold",
            "Wait: their post to our pick (reading, queue). Draft: LLM calls and repairs. Hold: draft checked to sent "
            "(pacing, rate limit). Fills in from the first reply written after the deploy.")
    q = status.get("queue") or {}
    waiting = q.get("candidates", refreshes[-1].get("candidates") if refreshes else None)
    groups_q = sum((g or {}).get("queued") or 0 for g in ((refreshes[-1].get("groups") if refreshes else None) or {}).values())
    if waiting is not None:
        row("speed", "Citizens waiting now", "grey", f"{max(waiting - groups_q, 0)}")

    # ---- volume ----
    live = [a for a in actions if a.get("live") is True and a.get("act") in WRITES]
    budget = (status.get("write_budget") or {}).get("limit") or TEAM_CAP_PER_MIN
    rate = sum(a["_t"] >= recent for a in live) / VOLUME_WINDOW_MIN
    share = rate / budget
    last_w = max((a["_t"] for a in live), default=None)
    row("volume", f"Posting, last {VOLUME_WINDOW_MIN} min",
        "green" if share >= VOLUME_GREEN else "amber" if share >= VOLUME_AMBER else "red",
        f"{rate:.1f}/min of {budget:g} ({share:.0%})" + ("" if rate else f" · last post {ago(now - last_w)}" if last_w else " · no posts"),
        f"≥ {VOLUME_GREEN:.0%} of budget",
        "Below the team budget: is the bot up and are the LLMs answering? Check Bot.")
    voices = (status.get("accounts") or {}).get("voices")
    if voices is not None:
        row("volume", "Voices in rotation", "amber" if voices < VOICES_MIN else "green", f"{voices}",
            f"≥ {VOICES_MIN} (our guess)", "Few voices: each posts more often and the rate drops. Add accounts.")
    n_lost = sum((f or {}).get("lost", {}).values()) if f else 0
    gate_lost = sum(1 for a in actions if a.get("act") == "lost" and str(a.get("why", "")).startswith("gate:")
                    and a.get("mode") in CITIZEN_WRITES and a["_t"] >= hour_ago)
    lost = (f or {}).get("lost") or {}
    row("volume", "Citizens lost, last full hour", "red" if n_lost or gate_lost else "green" if f else "grey",
        f"{n_lost}" if f else "no figures yet", "0",
        ("Lost: " + ", ".join(f"{v} {k}" for k, v in lost.items()) + ". Tell targeting / drafting.") if n_lost
        else "Citizens lost to rejections: tell the content session.")
    hour_writes = [a for a in live if a["_t"] >= hour_ago]
    acc = [a for a in hour_writes if a.get("act") in CITIZEN_WRITES and a.get("llm_calls") not in (None, "None")]
    first = sum(str(a.get("llm_calls")) == "1" for a in acc)
    share1 = first / len(acc) if acc else None
    row("volume", "Drafts passing first time", "grey" if share1 is None else "amber" if share1 < REACH_SHARE else "green",
        f"{share1:.0%}" if share1 is not None else "—", f"≥ {REACH_SHARE:.0%}",
        "Each rejection costs a repair call. The content session tunes the prompts.")
    cit = [a for a in hour_writes if a.get("act") in CITIZEN_WRITES and a.get("group") in (None, "None")]
    grp = [a for a in hour_writes if a.get("group") not in (None, "None")]
    r1, r2 = (sum(a.get("act") == k for a in cit) for k in ("reply", "reply_back"))
    row("volume", "Writes, last hour", "grey",
        f"{len(cit)} citizens ({r1} 1st reply · {r2} 2nd reply) · {len(grp)} groups · {len(hour_writes) - len(cit) - len(grp)} other · "
        f"{max(TEAM_CAP_PER_MIN * 60 - len(hour_writes), 0)} spare", f"of {TEAM_CAP_PER_MIN * 60}")

    # ---- conversion ----
    minds = _minds(points, day_start)
    cit_today = sum(1 for a in live if a.get("act") in CITIZEN_WRITES and a["_t"] >= day_start)
    net = minds["toward"] - minds["away"]
    row("conversion", "Changes of mind today", "green" if net > 0 else "red" if net < 0 else "amber",
        f"net {net:+d}".replace("+0", "0") + f": {minds['toward']} toward No · {minds['away']} away · {minds['neither']} neither ({cit_today} replies)",
        "toward > away (equal: amber)", "Replies aren't moving people toward No: see the todo/20 read-out.")

    for r in rows:
        r["note"] = next((v for k, v in (notes or {}).items() if r["name"].startswith(k)), "")
    order = {"red": 3, "amber": 2, "green": 1, "grey": 0}
    def worst(group):
        lights = [r["light"] for r in rows if r["group"] == group]
        return max(lights, key=order.get, default="grey")
    heads = dict(speed=f"{mf:.1f} min" if mf is not None else "—",
                 volume=f"{rate:.1f}/min", conversion=f"+{minds['toward']} / −{minds['away']}")
    subs = dict(speed="to reply" if mf is not None else "no replies timed",
                volume=f"of {budget:g} · {voices if voices is not None else '?'} voices",
                conversion="toward / away today")
    items = [dict(key=k, name=k.capitalize(), light=worst(k), head=heads[k], sub=subs[k],
                  rows=[r for r in rows if r["group"] == k]) for k in ("speed", "volume", "conversion")]
    extra = []
    skipped = (f or {}).get("skipped") or {}
    if skipped:
        extra.append("Skipped on purpose (last full hour): "
                     + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in sorted(skipped.items(), key=lambda kv: -kv[1])))
    if groups_q:
        extra.append(f"{groups_q} extra-group posts queued")
    return dict(lights=items, rows=rows, extra=extra, fixes=[r for r in rows if r["light"] in ("amber", "red")],
                light=max((i["light"] for i in items), key=order.get))


def account_days(log, now):
    """Accounts by competition (Sydney) day, newest first, and the suspended accounts newest first, from the portal's
    account_log (activity.csv: the team's registered/banned counts and the moderator's suspension messages)."""
    counts = [dict(c, _t=ts(c["ts"])) for c in (log or {}).get("counts") or [] if ts(c.get("ts"))]
    sus = [dict(x, _t=ts(x["ts"])) for x in (log or {}).get("suspended") or [] if ts(x.get("ts"))]
    if not counts:
        return [], []
    day = lambda t: t.astimezone(SYDNEY).date()
    today, d, prev, rows = day(now), day(counts[0]["_t"]), dict(registered=0, banned=0), []
    while d <= today:
        upto = [c for c in counts if day(c["_t"]) <= d]
        end = upto[-1] if upto else prev
        why = [x["why"] for x in sus if day(x["_t"]) == d]
        rows.append(dict(day=perth_span(d), today=d == today, registered=end["registered"], banned=end["banned"],
                         new_reg=end["registered"] - prev["registered"], new=end["banned"] - prev["banned"],
                         why=" · ".join(f"{w} ×{why.count(w)}" for w in dict.fromkeys(why))))
        prev, d = end, d + dt.timedelta(days=1)
    listed = [dict(time=perth(x["_t"]).strftime("%a %H:%M"), username=x["username"], id=x["id"], why=x["why"])
              for x in sorted(sus, key=lambda x: x["_t"], reverse=True)]
    return rows[::-1], listed


def gather(root, now, service):
    """Everything the page shows, as plain values. root is the repo checkout (logs/ and data/ under it)."""
    logs, data = root / "logs", root / "data"
    day_start = sydney_midnight(now.astimezone(SYDNEY).date())
    hour_ago = now - dt.timedelta(hours=1)
    status = read_json(data / "status.json") or {}
    status_t = ts(status.get("ts"))
    portal = read_json(data / "portal.json") or {}               # swan_dash/portal.py: leaderboard + points log
    portal_t = ts(portal.get("ts"))
    points = [dict(e, _t=ts(e["ts"])) for e in portal.get("events") or []
              if ts(e.get("ts")) and e.get("points") is not None]
    actions = [a for a in tail_jsonl(logs / "swan_actions.jsonl") if ts(a.get("ts"))]
    for a in actions:
        a["_t"] = ts(a["ts"])

    # ---- vitals ----
    live_writes = [a for a in actions if a.get("act") in WRITES and a.get("live") is True]
    writes_hour = sum(a["_t"] >= hour_ago for a in live_writes)
    rejects_hour = sum(a.get("act") == "reject" and a["_t"] >= hour_ago for a in actions)
    last_write = max((a["_t"] for a in live_writes), default=None)
    chain = status.get("llm") or []
    current = next((i for i, m in enumerate(chain) if not m.get("parked_until")), None)
    parked = [dict(model=m["model"], why=m.get("why") or "parked",
                   until=hm(dt.datetime.fromtimestamp(m["parked_until"], dt.timezone.utc)))
              for m in chain if m.get("parked_until")]
    # Each kind of draft tries the models in its own order (config.REPLY_MODELS, AMP_MODELS), so the first ready model
    # in the chain is not necessarily the one doing the work: show what each model actually answered today.
    calls = (read_json(data / "llm_usage.json") or {}).get(now.astimezone(QUOTA_DAY).date().isoformat(), {})
    states = [dict(model=m["model"], calls=calls.get(m["model"], 0),
                   state=f"{m.get('why') or 'parked'} until {hm(dt.datetime.fromtimestamp(m['parked_until'], dt.timezone.utc))}"
                   if m.get("parked_until") else "ready", out=bool(m.get("parked_until")))
              for m in chain]
    busiest = max(states, key=lambda s: s["calls"], default=None)
    acc = status.get("accounts") or {}
    per_min = status.get("per_min")

    acct_days, banned_list = account_days(portal.get("account_log"), now)

    facts = fact_desk(root, now)
    blue = blue_panel(data, now, points, day_start, logs)

    # ---- banner: the first problem wins, worst first ----
    try:                                       # deploy/healthcheck.sh's current problem, the same text it alerts with
        health = (data / "health_state").read_text().strip()
    except FileNotFoundError:
        health = ""
    stale = status_t is None or (now - status_t).total_seconds() > STALE_STATUS_S
    red = amber = None
    if service not in (None, "active"):
        red = f"DOWN: swan-bot is {service}. On the box: journalctl -u swan-bot -n 50"
    elif health:
        red = health
    elif chain and current is None and min(m["parked_until"] for m in chain) - now.timestamp() >= STALL_S:
        first = min(m["parked_until"] for m in chain)
        red = f"STALLED: every LLM is parked until {hm(dt.datetime.fromtimestamp(first, dt.timezone.utc))}"
    elif chain and current is None:              # a short gap: the bot waits a minute and carries on
        first = min(m["parked_until"] for m in chain)
        amber = f"LLMS BUSY: every model is rate-limited, next free at {hm(dt.datetime.fromtimestamp(first, dt.timezone.utc))}"
    elif stale:
        amber = ("NO STATUS: the bot hasn't reported for "
                 + (ago(now - status_t).replace(" ago", "") if status_t else "a while (or isn't live)"))
    elif current is not None and current >= DEGRADED_FROM:
        top = chain[0]
        amber = f"DEGRADED: on fallback LLM {chain[current]['model']} ({top['model']}: {top.get('why') or 'parked'})"
    elif status.get("rate_limited_last_hour"):
        amber = f"RATE-LIMITED: {status['rate_limited_last_hour']} × 429 in the last hour"
    elif portal.get("error"):
        amber = f"PORTAL: {portal['error']}"
    elif portal and (portal_t is None or (now - portal_t).total_seconds() > PORTAL_STALE_S):
        amber = "PORTAL: no score update for " + (ago(now - portal_t).replace(" ago", "") if portal_t else "a while")
    elif facts and facts["paused"]:
        amber = (f"FACT PAUSED: {', '.join(p['fact'] for p in facts['paused'])} (the bot leaves it out). "
                 + ("The desk decides it on its next hourly run (Facts, below)" if facts["auto"]["on"]
                    else "Review it under Facts below"))
    elif facts and facts["auto"]["problems"]:
        amber = f"FACTS: {facts['auto']['problems'][0]}"
    if red:
        banner = dict(level="red", text=red)
    elif amber:
        banner = dict(level="amber", text=amber)
    else:
        banner = dict(level="green", text="running · last post " + (ago(now - last_write) if last_write else "—"))
    if not blue:
        blue_banner = dict(level="amber", text="not running")
    elif blue["own"] and blue["own"]["hits"]:
        blue_banner = dict(level="red", text=f"{blue['own']['hits']} report(s) against our own accounts. Stop: ssh swan-ec2 'touch ctn/BLUE_OFF'")
    elif blue["stale"]:
        blue_banner = dict(level="amber", text=f"no status for {blue['ago'].replace(' ago', '')}. On the box: journalctl -u swan-blue -n 50")
    elif blue["waiting"]:
        blue_banner = dict(level="amber", text=f"{blue['waiting']} reports wait for your approval")
    elif blue["locked"]:
        blue_banner = dict(level="amber", text=f"locked until {blue['locked']}" + (f" · {blue['pending']}/{blue['cap']} pending" if blue["pending"] else ""))
    else:
        blue_banner = dict(level="green", text="running" + (f" · {blue['pending']}/{blue['cap']} pending" if blue["pending"] else ""))

    draft_banner = drafting_state(actions, data, now)

    # ---- score (typed in by hand: scripts/score.sh) ----
    entries = [e for e in (read_json(data / "score.json") or []) if ts(e.get("ts"))]
    score = None
    if entries:
        e = entries[-1]
        before = [x for x in entries if ts(x["ts"]) < day_start]
        delta = e["score"] - before[-1]["score"] if before else None
        hours = (ts(e["ts"]) - day_start).total_seconds() / 3600
        score = dict(points=e["score"], rank=e.get("rank"), teams=e.get("teams"), by=e.get("by", "?"),
                     ago=ago(now - ts(e["ts"])), delta=delta,
                     per_hour=round(delta / hours) if delta is not None and hours >= 0.5 else None,
                     last_hour=None, last_hour_at=None)
        if points:                             # the portal's own points log is exact: use it for today and last hour
            newest = max(e["_t"] for e in points)
            score["delta"] = sum(e["points"] for e in points if e["_t"] >= day_start)
            score["last_hour"] = sum(e["points"] for e in points if (newest - e["_t"]).total_seconds() < 600)
            score["last_hour_at"] = hm(newest)
    board = dict(leader=portal.get("leader"), above=portal.get("above"), below=portal.get("below"),
                 rank=portal.get("rank"), score=portal.get("score")) if portal.get("rank") else None
    def replies_between(lo, hi):               # our 1st / 2nd replies in a window: counts only, the portal's points are not split by kind
        return tuple(sum(1 for a in live_writes if a.get("act") == k and lo < a["_t"] <= hi) for k in ("reply", "reply_back"))
    history = [dict(time=perth(ts(x["ts"])).strftime("%a %H:%M"), score=x["score"], rank=x.get("rank"),
                    replies=replies_between(ts(entries[i - 1]["ts"]), ts(x["ts"])) if i else None,
                    change=x["score"] - entries[i - 1]["score"] if i else None, by=x.get("by", "?"),
                    # the portal's own notes behind this change (Marc: "details in place"), newest first
                    notes=[dict(time=hm(e["_t"]), points=e["points"], text=short(e.get("message"), 300))
                           for e in sorted(points, key=lambda e: e["_t"], reverse=True)
                           if i and ts(entries[i - 1]["ts"]) < e["_t"] <= ts(x["ts"])])
               for i, x in enumerate(entries)][-10:][::-1]
    today = now.astimezone(SYDNEY).date()
    poll = next(((d, name, need) for d, name, need in POLLS if d >= today), None)
    milestone = None
    if poll:
        d, name, need = poll
        have = score["points"] if score else None
        milestone = dict(name=name, date=d.strftime("%a %-d %b"), need=need,
                         reached=have is not None and have >= need,
                         short=None if have is None else max(0, need - have),
                         today=d == today)
    mult_now = next((m for d, m in reversed(MULTIPLIERS) if d <= today), 1)
    nxt = next(((d, m) for d, m in MULTIPLIERS if d > today), None)
    multiplier = dict(now=mult_now, next=nxt and nxt[1], date=nxt and nxt[0].strftime("%a %-d %b"),
                      left=nxt and until(sydney_midnight(nxt[0]) - now))

    # ---- activity: our writes, account events, long LLM parks, deploys and alerts (points: under Score) ----
    rows = conversations(actions, post_texts(actions, data))
    for a in actions:
        act = a.get("act")
        if act == "register":
            rows.append(dict(t=a["_t"], who=a.get("persona") or a.get("role") or "", what="new account",
                             text=a.get("username"), kind="event"))
        elif act == "suspended":
            rows.append(dict(t=a["_t"], who="", what="SUSPENDED", text=a.get("username"), kind="susp"))
        elif act == "llm_park":
            u = ts(a.get("until"))
            if u and (u - a["_t"]).total_seconds() >= LONG_PARK_S:
                rows.append(dict(t=a["_t"], who="", what="LLM parked", kind="event", family="ops",
                                 model=a.get("model"), why=a.get("why"), until=hm(u),
                                 text=f"{a.get('model')}: {a.get('why')} until {hm(u)}"))
    for line in tail_lines(logs / "alerts.log"):
        t, _, msg = line.partition(" ")
        if ts(t):
            msg = msg.removeprefix("[swan-ec2] ")
            if msg.startswith("deployed"):
                subject = re.sub(r"^(\w{7}) [^:]{1,60}: ", r"\1 ", msg.removeprefix("deployed "))   # drop the author
                rows.append(dict(t=ts(t), who="", what="deploy", text=short(subject),
                                 kind="event", family="ops"))
            elif "hidden by the moderator" in msg:          # deploy/healthcheck + swan-watch: a voice lost a post
                rows.append(dict(t=ts(t), who="", what="post hidden", text=short(msg, 200), kind="hidden"))
            else:                                           # each alert kind its own colour (Marc, 22 Oct)
                what, kind = next(((w, k) for rx, w, k in ALERT_KINDS if re.match(rx, msg)), ("alert", "event"))
                rows.append(dict(t=ts(t), who="", what=what, text=short(msg, 200), kind=kind))
    rows.sort(key=lambda r: r.get("last") or r["t"], reverse=True)   # a conversation moves up when it gets more
    for r in rows:
        r.setdefault("time", hm(r["t"]))
        r.setdefault("post", None)
    items = bundle(rows)

    # ---- the trending pulse the bot writes towards (todo/15): its newest "pulse" record ----
    p = next((a for a in reversed(actions) if a.get("act") == "pulse"), None)
    pulse = p and dict(id=p.get("id"), ago=ago(now - p["_t"]),
                       stale=(now - p["_t"]).total_seconds() > PULSE_MAX_AGE_S,
                       hooks=[short(h.get("text")) for h in p.get("hooks") or [] if isinstance(h, dict)],
                       no_shapes=[short(x) for x in p.get("no_shapes") or []],
                       yes_lines=[short(x) for x in p.get("yes_lines") or []],
                       avoid=[short(x) for x in p.get("avoid") or []])

    every = tail_jsonl(logs / "deploys.jsonl", 200_000)
    deploys = [d for d in every if d.get("result") == "ok"]
    running = dict(sha=deploys[-1]["new"][:7], prev=deploys[-1]["old"][:7], when=hm(ts(deploys[-1]["ts"])),
                   light="green" if every[-1] is deploys[-1] else "red",
                   failed=hm(ts(every[-1]["ts"])) if every[-1] is not deploys[-1] else None) if deploys else None

    rc = reach(actions, status, points, now, day_start, read_json(data / "reach_notes.json") or {})
    today_acct = next((d for d in acct_days if d["today"]), None)
    bans = today_acct["new"] if today_acct else 0
    hidden_today = sum(1 for r in rows if r.get("kind") == "hidden" and r["t"] >= day_start)
    srows = [dict(group="stealth", name="New bans today", light="green" if bans == 0 else "amber" if bans <= STEALTH_BANS_DAY else "red",
                  now=f"{bans}" + (f" · {today_acct['why']}" if today_acct and today_acct["why"] else ""),
                  target=f"0 (amber up to {STEALTH_BANS_DAY:.0f}: {TOTAL_CAP} accounts over 14 days)", fix="Accounts are being caught: see the list under Bot > Accounts by day and todo/31.", note=""),
             dict(group="stealth", name="Posts hidden today", light="amber" if hidden_today else "green", now=f"{hidden_today}",
                  target="0", fix="3 hidden posts suspend an account. See Activity.", note=""),
             dict(group="stealth", name="Banned in total", light="grey",
                  now=f"{acct_days[0]['banned']} of {acct_days[0]['registered']} registered" if acct_days else "—", target="", fix="", note="")]
    rc["rows"] += srows
    rc["fixes"] += [r for r in srows if r["light"] in ("amber", "red")]
    order = {"red": 3, "amber": 2, "green": 1, "grey": 0}
    rc["lights"].append(dict(key="stealth", name="Stealth", rows=srows, head=f"{bans} bans", sub="today · " + f"{hidden_today} hidden posts",
                             light=max((r["light"] for r in srows), key=order.get)))
    rc["light"] = max((i["light"] for i in rc["lights"]), key=order.get)
    levels = (banner["level"], blue_banner["level"], draft_banner["level"], rc["light"])
    return dict(
        now=hm(now), banner=banner, blue_banner=blue_banner, draft_banner=draft_banner, acct_days=acct_days, banned_list=banned_list,
        worst="red" if "red" in levels else "amber" if "amber" in levels else "green",
        status_word=STATUS_WORD["red" if "red" in levels else "amber" if "amber" in levels else "green"], score=score, history=history, board=board, milestone=milestone,
        multiplier=multiplier, portal_accounts=portal.get("accounts"), score_lines=score_lines(points, day_start),
        portal_checked=ago(now - portal_t) if portal_t else None,
        day_start=perth(day_start).strftime("%-I%p").lower(),
        writes=dict(hour=writes_hour, planned=round(per_min * 60) if per_min else None, cap=TEAM_CAP_PER_MIN * 60),
        accounts=dict(live=acc.get("live"), live_cap=LIVE_CAP, used=acc.get("used"), total_cap=TOTAL_CAP,
                      suspended=acc.get("suspended"), voices=acc.get("voices"), boosters=acc.get("boosters")),
        llm=dict(degraded=current is not None and current >= DEGRADED_FROM, model=chain[current]["model"] if current is not None else None,
                 rank=ordinal(current + 1) if current is not None else None, of=len(chain), parked=parked,
                 chain=states, busiest=busiest if busiest and busiest["calls"] else None),
        errors=dict(rate_limited=status.get("rate_limited_last_hour"), rejects=rejects_hour),
        activity=items[:ACTIVITY_TOP], older=items[ACTIVITY_TOP:ACTIVITY_ALL], running=running, pulse=pulse, facts=facts,
        blue=blue, reach=rc,
        rollback=ROLLBACK.format(prev=running["prev"]) if running and banner["level"] == "red" else None,
        built=perth(now).strftime("%H:%M:%S"))


def render(ctx, template="index.html.j2"):
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(pathlib.Path(__file__).parent / "templates"),
                             autoescape=True, undefined=jinja2.StrictUndefined, trim_blocks=True, lstrip_blocks=True)
    env.filters["n"] = lambda x: "—" if x is None else f"{x:,}"
    env.filters["short"], env.filters["hm"] = short, hm
    return env.get_template(template).render(ctx)


def write_atomic(path, text):
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=pathlib.Path, required=True, help="directory nginx serves")
    ap.add_argument("--root", type=pathlib.Path, default=ROOT, help="repo checkout with logs/ and data/")
    args = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    html = render(gather(args.root, now, service_state()))
    args.out.mkdir(parents=True, exist_ok=True)
    write_atomic(args.out / "index.html", html)
    (args.out / "lab.html").unlink(missing_ok=True)      # the NPC lab page, retired 2026-10-23 (todo/33)
    write_atomic(args.out / "robots.txt", "User-agent: *\nDisallow: /\n")
    write_atomic(args.out / "app.js", (pathlib.Path(__file__).parent / "templates" / "app.js").read_text())


if __name__ == "__main__":
    main()
