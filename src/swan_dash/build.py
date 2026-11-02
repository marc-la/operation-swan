"""Build the team dashboard (todo/09): one static HTML page from the bot's own files. swan-dash.timer runs it every
minute on EC2 and nginx serves the result behind a password.

    python -m swan_dash.build --out /var/www/swan        # (from src/) what the timer runs
    python -m swan_dash.build --out /tmp/swan            # local preview from this checkout's logs/ and data/

It reads logs/ and data/ only. It never opens .env or secrets/ (the systemd unit also makes them inaccessible) and
needs no network. Every value on the page is picked field by field; whole records are never rendered.
"""
import argparse
import collections
import datetime as dt
import json
import math
import os
import pathlib
import re
import subprocess
import tomllib
from zoneinfo import ZoneInfo

import jinja2

from swan_blue.evidence import awards_by_rate, first_later
from swan_bot import config as bot_config
from swan_bot.analysis import parse_activity
from swan_dash import sides as team_sides
from swan_dash.portal import FINALISTS, TEAM_NAME  # constants only (FACTDESK_AUTO): it reads no .env on import
try:
    from swan_bot import budget      # todo/39: the ban forecast (pure). Not merged yet: the forecast rows are left out
except ImportError:
    budget = None

ROOT = pathlib.Path(__file__).resolve().parents[2]
PERTH = ZoneInfo("Australia/Perth")
SYDNEY = ZoneInfo("Australia/Sydney")          # competition days roll over at midnight Sydney (9pm Perth)
QUOTA_DAY = ZoneInfo("America/Los_Angeles")    # data/llm_usage.json days (swan_bot/llm.py): free quotas reset there
TEAM_CAP_PER_MIN = 3                           # posts + replies + reposts, team-wide (rules)
LIVE_CAP, TOTAL_CAP = 50, 200                  # accounts alive at once / ever
WRITES = {"post": "post", "reply": "1st reply", "second_voice": "2nd voice", "reply_back": "2nd reply",
          "journalist": "journalist", "thread": "own thread", "thread_answer": "thread answer", "repost": "repost"}
STATUS_WORD = {"green": "RUNNING", "amber": "ALERT", "red": "DOWN"}
FINAL_FILE = "FINAL"           # touched on the box at the 2 Nov 18:00 AEDT lockout: bot and Blue stopped on purpose, page word FINAL   # browser tab title (a colour word clashes with the Red track)
# poll awards and Red multiplier changes, as Sydney calendar dates (docs/01-competition/schedule.md)
POLLS = [(dt.date(2026, 10, 21), "Poll 1", 1), (dt.date(2026, 10, 25), "Poll 2", 7000),   # 7,000 since 20 Oct
         (dt.date(2026, 10, 29), "Poll 3", 7000)]
MULTIPLIERS = [(dt.date(2026, 10, 26), 2), (dt.date(2026, 11, 1), 4)]     # derived, not confirmed by organisers
LOG_TAIL_BYTES = 6_000_000                     # likes are logged one per line; this covers several hours
STALE_STATUS_S = 300
DEGRADED_FROM = 5                              # index in the LLM chain: the 6th model or lower is degraded (Marc, 22 Oct)
STALL_S = 5 * 60                               # every LLM parked this long or longer: red
PORTAL_STALE_S = 45 * 60                       # swan-portal.timer checks every minute; a full read is due at :02 and :32
PULSE_MAX_AGE_S = 2 * 3600                     # swan_bot config.PULSE_MAX_AGE_S: older, the bot doesn't use it
ACTIVITY_TOP, ACTIVITY_OLDER = 12, 40        # rows always shown / most rows behind "Older activity"
CRITICAL_KINDS = {"susp", "hidden", "deployfail", "bad", "blue"}   # older activity keeps these and the budget / ring alerts
CRITICAL_WHAT = {"alert"}                                           # (what no pattern in ALERT_KINDS claimed); not writes,
                                                                    # LLM parks, deploys, new accounts or the pool's repeated status


def critical(row):
    """Older activity is for the events worth a second look (Marc, 24 Oct): bans, hidden posts, failed deploys, service
    down, Blue rulings and the budget / ring alerts. A good deploy is the version chip's job, the pool's runway and
    card lines are tiles, so none of those take a place here."""
    return row["kind"] in CRITICAL_KINDS or row.get("what") in CRITICAL_WHAT


def older_critical(items):
    """The critical rows behind the top of the log, back-to-back deploys bundled again once the parks are gone."""
    rows = [r for i in items for r in (i["rows"] if i["kind"] == "group" else [i])]
    return bundle([r for r in rows if critical(r)])[:ACTIVITY_OLDER]


HIDE_RX = re.compile(r"@(\w+): post #(\d+) hidden by the moderator \((\d+) hidden(?:, (\d+) actions)?")
HIDE_STOP = 3                                  # swan_bot config: 3 hidden posts suspend an account
RISKY_ACTIONS = 100                            # with 1+ hidden and this many actions, one upheld account report suspends too


def hidden_row(t, msg):
    """A 'hidden by the moderator' alert as who / what happened / how close to a suspension, without the rule text the
    watch job puts in the channel message. A line that doesn't parse stays whole."""
    m = HIDE_RX.match(msg)
    if not m:
        return dict(t=t, who="", what="post hidden", text=" ".join(msg.split()), kind="hidden")
    user, pid, n, actions = m[1], m[2], int(m[3]), m[4] and int(m[4])
    step = (re.search(r"Bot: ([^.]+)\.", msg) or [None, None])[1]
    bits = [f"post #{pid}", f"hide {n} of {HIDE_STOP}"]
    if actions is not None:
        bits.append(f"{actions} actions")
        if actions >= RISKY_ACTIONS:
            bits.append("one upheld report would suspend it")
    if step and step != "no change":
        bits.append(f"bot {step}")
    return dict(t=t, who=f"@{user}", what="post hidden", text=" · ".join(bits), kind="hidden")


def alert_key(text):
    """The alert with its numbers blanked, so 'spare 117, 7.2 d' and 'spare 116, 7.1 d' are one alert (swan_bot.budget)."""
    return re.sub(r"\d+(?:[.,]\d+)?", "#", text)


REPEAT_KINDS = {"pool", "event"}               # alerts that are a state, not an event: the same line again is one row
BLUE_MERGE_S = 30 * 60                         # Blue rulings this close together are one row
GENUINE_RX = re.compile(r"BLUE: #(\d+) ruled genuine")


def collapse(rows):
    """Repeats of one alert become one row at the newest time, '×6 since 17:34'; Blue 'ruled genuine' rulings within
    BLUE_MERGE_S of each other become one row that opens to list them (todo: activity log, Marc, 24 Oct)."""
    rows = sorted(rows, key=lambda r: r["t"], reverse=True)         # newest first, like the log
    out, seen = [], {}
    for r in rows:
        if r.get("what") in ("pool", "alert") and r["kind"] in REPEAT_KINDS:
            first = seen.get((r["what"], alert_key(r["text"])))
            if first:
                first["n"] += 1
                first["since"] = hm(r["t"])
                first["text"] = f"{first['base']}  ×{first['n']} since {first['since']}"
                continue
            r.update(n=1, base=r["text"])
            seen[(r["what"], alert_key(r["text"]))] = r
        out.append(r)
    genuine = [r for r in out if r["kind"] == "blue" and GENUINE_RX.match(r["text"])]
    rest = [r for r in out if not any(r is g for g in genuine)]
    clusters = []                                                     # genuine rulings, newest first, near ones together
    for r in genuine:
        if clusters and (clusters[-1][-1]["t"] - r["t"]).total_seconds() <= BLUE_MERGE_S:
            clusters[-1].append(r)
        else:
            clusters.append([r])
    for c in clusters:
        if len(c) == 1:
            rest.append(c[0])
            continue
        ids = ", ".join(f"#{GENUINE_RX.match(x['text'])[1]}" for x in c)
        rest.append(dict(t=c[0]["t"], who="", what="Blue", kind="blue", id=f"b-{int(c[0]['t'].timestamp())}",
                         text=f"{len(c)} reports ruled genuine ({ids})", detail=[(hm(x["t"]), x["text"]) for x in c]))
    return rest
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


def tail_lines(path, n=300):
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


def hm_day(t, now):
    """Clock time, with the Perth day added once it is not today: '14:05', 'yesterday 14:05', 'Sun 25 Oct 14:05'."""
    days = (perth(now).date() - perth(t).date()).days
    if days == 0:
        return hm(t)
    return f"{'yesterday' if days == 1 else perth(t).strftime('%a %-d %b')} {hm(t)}"


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
        parts = [f"{len(deploys)} deploy{'s' if len(deploys) > 1 else ''} (latest {short(deploys[0]['text'])})"] if deploys else []
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


def leaderboard_rows(portal):
    """The leaderboard as the team reads it: the finalist places (top three, who fly to Sydney), a line, then us with
    the team above and below. Teams already in the top three are not repeated; `gap` is set where ranks are skipped
    between the two blocks, and `between` lists those teams for the expandable row. `cutoff` is how far we are behind third place (None when we are in the top three)."""
    us = dict(rank=portal["rank"], team="Operation Swan (us)", score=portal["score"], us=True)
    top = [r for r in portal.get("top") or ([portal["leader"]] if portal.get("leader") else []) if r["rank"] <= FINALISTS]
    shown = {r["rank"] for r in top}
    near = [dict(us=False, **r) if r is not us else r for r in (portal.get("above"), us, portal.get("below"))
            if r and r["rank"] not in shown]
    third = next((r for r in top if r["rank"] == 3), None)
    gap = bool(near) and bool(top) and near[0]["rank"] > top[-1]["rank"] + 1
    between = [r for r in portal.get("rows") or [] if gap and top[-1]["rank"] < r["rank"] < near[0]["rank"]]
    return dict(finalists=[dict(r, us=r["rank"] == us["rank"]) for r in top], near=near,
                gap=gap, between=between,
                cutoff=max(third["score"] - us["score"], 0) if third and us["rank"] > 3 else None)


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
ALERT_KINDS = [(r"POOL( \(dry run\))?( RUNWAY|: no free persona card)", "pool", "pool"),   # a standing state: the Pool tile has it
               (r"DEPLOY FAILED", "deploy failed", "deployfail"), (r"BLUE", "Blue", "blue"),
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
    # stays until a human rules on each proposal the failed run held back (facts_review.py: accept or reject), or 24 h
    tested = [r for r in autolog if "tests/test_facts.py failed" in (r.get("summary") or "")
              and last.get(r.get("id")) is r and r.get("id") not in decided
              and (now - (ts(r.get("decided_at")) or MIN_T)).total_seconds() < DESK_PROBLEM_S]
    if tested:
        ids = ", ".join(f"#{r['id']}" for r in sorted(tested, key=lambda r: r["id"]))
        problems.append(f"tests/test_facts.py failed with the desk's changes at {hm(ts(tested[-1]['decided_at']))}: "
                        f"none of them went live; waiting for your ruling: {ids}")
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
BLUE_FILL_GREEN, BLUE_FILL_AMBER = 0.8, 0.5     # pending reports / the cap: every slot is a ruling coming in 3 h, so empty slots are lost points (Marc, 24 Oct)
BLUE_STALE_S = 10 * 60                         # swan-blue writes its status every minute
# Red is down: back to the commit before the running one. swan-update.timer would pull origin/main again within 2 min,
# so it is paused first; start it again once a fix is pushed.
ROLLBACK = ("ssh swan-ec2 'cd ctn && sudo systemctl stop swan-update.timer && git reset --hard {prev} && "
            "sudo systemctl restart swan-bot swan-blue'")
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
BLUE_REDUCED_WARN = 1 / 3                      # a third or more of a finished day's awards paid reduced: amber (blue-reporting.md §10's trigger; 24 Oct was 46%)
BLUE_MSG = re.compile(r"moderat|inauthentic|suspen", re.I)


def blue_pending(pend, cap):
    """Pending reports as "n/cap pending", never over the cap (30 Oct, Marc: "36/30 pending" read as a bug). swan-blue's
    ledger can run over it: a co-reported post is ruled before its 3 h and an account ruling shows only in the portal
    log, so the ledger still counts them while the platform has already freed their slots and takes the one report a
    hold that swan-blue tries when full by its count. The platform never has more than the cap awaiting a ruling, so
    the page shows it full and names the rest. -> (shown, text, the ledger's extra)."""
    shown, extra = min(pend, cap), max(0, pend - cap)
    return shown, f"{shown}/{cap} pending", extra


def blue_ledger_note(extra):
    return f"{extra} more already ruled, still open in our ledger" if extra else ""


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
    rulings it covers: all suspended, all dismissed, or "k of n" when it's split. {key: (word, note, css, up)}: up is the
    share of that ruling counted as upheld (1, 0, k/n), None while the portal log has no outcome for it yet."""
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
                out[r.get("key")] = ("ruled", "outcome not in the portal log yet", "", None)
            else:
                batches.setdefault(id(run), (run, []))[1].append(r.get("key"))
    for run, keys in batches.values():
        k, n = min(run[1], len(keys)), len(keys)
        word = (("suspended", f"+{run[2]:g}", "up", 1) if k == n else ("dismissed", "no points, no lock", "", 0) if k == 0
                else ("unclear", f"{k} of these {n} were suspended, the rest dismissed; the portal doesn't say which", "", k / n))
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
        up = 1 if status == "hidden" else 0 if status == "genuine" else None      # share counted as a success
        if r.get("kind") != "post" and status == "ruled":
            out, note, css, up = outcomes.get(r.get("key"), ("ruled", "", "", None))
        when = ("rules " if status == "pending" else "") + (hm(t) if t else "")
        rows.append(dict(what=what, group=f"group {r.get('team') or '?'}", at=hm(t) if t else "", t=t,
                         status=status, out=out, note=note, css=css, up=up, key=f"{out}|{note}",
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
        # the day's filings still waiting for a ruling, from swan-blue. Not sent minus ruled: a ruling counts on the
        # day it was ruled, so a day's late filings ruled after midnight stayed "pending" there forever (25 Oct: 30
        # on Thu 22, all ruled Fri). The subtraction is only the fallback for a status file from before the field
        r["pending"] = a["pending"] if "pending" in a else max(0, r["filed"] - r["hidden"] - r["genuine"] - r["accounts"])
        # the share of awards paid at a reduced rate (the per-team daily rates cutting in); None when nothing was paid
        r["reduced"] = round(100 * (r["awards"] - r["full"]) / r["awards"]) if r["awards"] else None
        r["reduced_level"] = "" if r["today"] or r["reduced"] is None else \
            "warn" if r["reduced"] >= 100 * BLUE_REDUCED_WARN else "up"
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


def spread_line(spread):
    """One line for the spread caps swan-blue publishes in blue_status.json ('spread'): the caps (0 is off) and how
    many candidates they kept back in the latest ranking. None for an older status file without the field."""
    if not isinstance(spread, dict):
        return None
    cap = lambda k: spread.get(k) or 0
    held = spread.get("held") or {}
    thread, pending, day = cap("thread_max"), cap("label_pending_max"), cap("label_day_max")
    caps = ", ".join((f"{thread} per thread" if thread else "thread off",
                      " and ".join((f"{pending} pending" if pending else "pending off",
                                    f"{day} a day" if day else "a day off")) + " per cluster"))
    cluster = (held.get("label_pending") or 0) + (held.get("label_day") or 0)
    return f"spread caps: {caps}; held back now: thread {held.get('thread') or 0}, cluster {cluster}"


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
    # the lock's time is on the Blue tile only (Marc, 24 Oct); here just why
    bits = ([f"OUR OWN ACCOUNTS REPORTED: {own['hits']}"] if own and own["hits"] else []) + \
        ([f"{waiting} waiting for approval"] if waiting else []) + \
        ([f"locked ({lock_why})", f"{ready} ready"] if locked else []) + \
        ([blue_pending(s["pending"], s.get("cap") or s["pending"])[1] + (f", next ruling {hm(nxt)}" if nxt and not locked else "")]
         if s.get("pending") else []) + \
        ([f"{today.get('hidden', 0)} hidden since 9pm"] if today.get("filed") else []) + \
        ([f"{pts:+,} pts since 9pm"] if pts else [])
    rows_all = [r for it in timeline for r in (it["rows"] if it["kind"] == "run" else [it])]
    # Pending is what swan-blue still has pending (and a ruling the portal log hasn't reported yet). A ruled account
    # report the portal can't attribute ("k of n suspended") counts k/n success and the rest failed, so the three
    # numbers add up to the reports filed and the success and failed totals match the portal's.
    done = [r for r in rows_all if r["up"] is not None]
    counts = dict(success=round(sum(r["up"] for r in done)), failed=round(sum(1 - r["up"] for r in done)),
                  pending=len(rows_all) - len(done))
    return dict(
        stale=t is None or (now - t).total_seconds() > BLUE_STALE_S, ago=ago(now - t) if t else "never",
        summary=" · ".join(bits) or "nothing to report right now", why=s.get("why"),
        locked=hm(locked) if locked else None, lock_why=s.get("lock_why"), pending=s.get("pending"), cap=s.get("cap"),
        lock_estimate=s.get("lock_src") == "estimate", ready=ready, ready_accounts=s.get("ready_accounts") or 0,
        pg_max=s.get("pg_max"), pg_check={"n": 0, **(s.get("pg_check") or {})},
        clusters={"today": 0, "full": 0, **(s.get("clusters") or {})}, spread=spread_line(s.get("spread")),
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
REACH_SPEED_MIN, REACH_SPEED_RED = 3, 5   # a new citizen post answered within MIN (median) is green, up to RED amber, over red (Marc, 23 Oct: reach the bots within 5 min)
BACKLOG_MIN = 60               # a first reply to a post older than this when we sent it is backlog drain, not speed (Marc, 24 Oct: 2,000 waiting, 551 min median)
REACH_BACK_MIN = 1             # a citizen answering us gets our reply within this (median)
VOLUME_WINDOW_MIN = 30         # posting rate is measured over this long, so a stall or a recovery shows within minutes
VOLUME_GREEN, VOLUME_AMBER = 0.7, 0.35     # share of the team's 3 writes a minute: green at or above, red below AMBER
CATCHUP_BUCKET_S = 600         # speed leaves out catch-up: a post made in a 10 min bucket where we wrote under VOLUME_AMBER of budget
                               # (the box stalled, drafting starved) and then answered later than the bar (Marc, 23 Oct)
REACH_SHARE = 0.9              # answered / answerable, and drafts passing on the first LLM call
# ---- stealth as rates, and the bans forecast against a plan (todo/42, Marc 24 Oct) ----
PATH_GREEN_X, PATH_GREEN_MIN = 0.08, 3      # bans over the path now: green up to max(MIN, X of the path so far)...
PATH_AMBER_X, PATH_AMBER_MIN = 0.20, 8      # ...amber up to max(MIN, X), red beyond (a share of the path, so it holds for any pool size)
LEFT_AMBER_SHORT = 10                       # accounts left forecast on the goal day short of the goal by up to this: amber; more: red
# ---- engagement per write (Marc, 25 Oct; todo/46, docs/06-strategy/engagement-audit-2026-10-25.md) ----
ENG_POINTS = {"likes": 5, "reposts": 10, "replies": 15, "follows": 20, "unfollows": -20}   # base points of what NPCs do to our posts
ENG_WINDOW_H = 24              # the headline window: a whole day of NPC activity, so the time of day cancels out
ENG_LAG_H = 1                  # the portal books an hour's engagement ~1 h after it: the writes are those of the window ending 1 h earlier
ENG_MIN_WRITES, ENG_MIN_LINES = 500, 18   # fewer writes or portal lines in the window than this and the figure is shown grey
ENG_GREEN, ENG_AMBER = 6.0, 4.5   # base points per write: 24 h windows 23-25 Oct ran 4.5-5.9 (median 5.0). Red is below the worst of those; green is the goal, +1 on the median (Marc, 25 Oct: what the levers in the audit can add)
ENG_GOAL = ENG_GREEN           # the goal, shown on the tile
HIDE_TARGET = getattr(bot_config, "HIDE_RATE_TARGET", 0.014)   # hidden text posts / text writes: 1.4% now, 1.0% after todo/40
HIDE_WINDOW_H = 24             # trailing window of writes for the hide rate
HIDE_CENSOR_H = 3.6            # a hide takes ~3.3 h to show: only writes at least this old are counted (hide-risk analysis)
HIDE_MIN_N = 300               # fewer text writes than this and the rate is shown grey with its n
ROLL_MIN_BANS = 5              # writes per ban = text writes ÷ bans since the last this many bans (the headline and the forecast):
ROLL_MAX_H = 7 * 24            # under 5 bans a day a fixed 24 h window was mostly empty (Marc, 1 Nov); counted back no further than this
ROLL_HOURS, ROLL_LONG_H = 24, 72   # the same ratio over fixed windows, in the detail, to see which way it moves
FORECAST_FROM = dt.date(2026, 10, 24)    # the forecast table starts here (todo/39); earlier days are history only
BAN_TOL_SIGMA = 1.5            # net (actual - forecast) is inside the tolerance up to this many sqrt(forecast), at least 2
TEXT_WRITES = frozenset(WRITES) - {"repost"}   # replies, posts, threads: what a hide is counted against (not reposts)
LIFE_ACTS = frozenset(a.encode() for a in (*WRITES, "suspended"))
AUDIT_STALE_S = 4 * 3600       # data/pattern_audit.json (scripts/pattern_audit.py): older than this the pattern rows go grey
RUNWAY_AMBER_X = 1.5           # pool runway (days of spare accounts at today's loss rate) under days left: red; under 1.5x: amber
BUDGET_END_PERTH = "9pm Perth, Mon 2 Nov"      # the end of 2 Nov Sydney (midnight Sydney = 9pm Perth), for the days-left rows
POOL_ACTS = 5                  # the pool worker's last actions shown behind the Pool line
VOICES_MIN = 10                # a guess: fewer writers than this and throughput drops
MIND = re.compile(r"(\d+) (.*)")
LIGHT_TIPS = dict(      # the hover text on each tile: plain tolerances, no jargon (Marc, 23 Oct)
    speed=f"Speed: how long a citizen waits for our reply (median, last hour).\n"
          f"New citizen posts: green up to {REACH_SPEED_MIN} min · amber {REACH_SPEED_MIN}-{REACH_SPEED_RED} · red over {REACH_SPEED_RED}.\n"
          f"Citizens answering us: green up to {REACH_BACK_MIN} min · amber {REACH_BACK_MIN}-{3 * REACH_BACK_MIN} · red over {3 * REACH_BACK_MIN}.\n"
          f"The time splits into wait (their post until we pick it up), draft (writing the reply) and hold (waiting to send).\n"
          f"Only replies to posts under {BACKLOG_MIN} min old when we answered are timed; replies that drain the queue behind them are\n"
          f"counted on their own grey row (Backlog drained), so a long queue no longer turns Speed red.\n"
          f"Replies to posts from an outage backlog are left out; the row says how many.",
    volume=f"Volume: how much we post. The team limit is {TEAM_CAP_PER_MIN} a minute.\n"
           f"Posting rate, last {VOLUME_WINDOW_MIN} min: green {VOLUME_GREEN * TEAM_CAP_PER_MIN:g}+ a minute · amber "
           f"{VOLUME_AMBER * TEAM_CAP_PER_MIN:g}-{VOLUME_GREEN * TEAM_CAP_PER_MIN:g} · red under {VOLUME_AMBER * TEAM_CAP_PER_MIN:g}.\n"
           f"Voices writing: amber if under {VOICES_MIN}.\n"
           f"Citizens lost in the last full hour: red if any.\n"
           f"Drafts passing first time is shown, not graded.",
    conversion="Conversion: are our replies moving people toward No? Net = changes of mind toward us minus away, today.\n"
               "Green: net above 0 · amber: net 0 · red: net below 0.",
    stealth=f"Stealth: accounts the moderator has banned. Big number: all banned so far (the portal's count; its list of names can lag). "
            f"Small: new bans since 9pm Perth, where we are heading by tonight (banned now plus the rest of today's plan at the measured writes per ban), and the aim for tonight (config.BAN_PATH: 40 banned by the end of 24 Oct, 50, 60, 80 on 28 Oct, 140 on 31 Oct) with how far over or under it we are heading.\n"
            f"The colour is the gap between the forecast for tonight and the path: green up to {PATH_GREEN_X:.0%} of it (at least {PATH_GREEN_MIN}) over · amber up to {PATH_AMBER_X:.0%} (at least {PATH_AMBER_MIN}) · red beyond. Grey when there is no path for the day.\n"
            f"Hidden posts and today's bans are shown in the detail but do not change the colour.\n"
            f"Pattern score (scripts/pattern_audit.py): how much our writes read like a rota, 0-100. In the detail, not counted in the colour (Marc, 24 Oct).",
    hide=f"Hide rate: hidden text posts / text writes, last {HIDE_WINDOW_H} h, counting writes at least {HIDE_CENSOR_H:g} h old (a hide takes about 3.3 h to show), 95% interval.\n"
         f"Green when the interval is under the {HIDE_TARGET:.1%} target, red when over, amber when it straddles; grey under {HIDE_MIN_N} writes.",
    life=f"Writes per ban: text writes ÷ accounts banned, over the time the last {ROLL_MIN_BANS} bans took (at most {ROLL_MAX_H // 24} days). Higher is better. The bans forecast divides planned writes by it.\n"
         f"Under {ROLL_MIN_BANS} bans in {ROLL_MAX_H // 24} days it is too noisy: the forecast uses the default instead. Not graded.",
    accounts=f"Accounts: voices writing now, then accounts alive (at most {LIVE_CAP} at once) and registered (at most {TOTAL_CAP} in all).\n"
             f"Amber: fewer than {VOICES_MIN} voices, or the pool is sagging. Red: the pool is low. A dry-run pool never colours it.\n"
             f"Hot mode (SWAN_HOT_VOICES): one voice writes on purpose, so the count is not graded. Green: one writing and a spare waiting · amber: no spare left · red: none left, the bot is idle.",
    blue=f"Blue: reports waiting for a ruling, out of the {{cap}} the team may have pending. Each full slot is a ruling due about 3 h after filing, so the aim is to keep them full.\n"
         f"Green: {BLUE_FILL_GREEN:.0%} or more full · amber: {BLUE_FILL_AMBER:.0%}-{BLUE_FILL_GREEN:.0%} · red: under {BLUE_FILL_AMBER:.0%}, or swan-blue silent · grey: locked for 6 h after a 'genuine' ruling (nothing to do).\n"
         f"Successful and failed are the reports ruled since 9pm Perth (the ledger under Blue). No tile changes the page's RUNNING / ALERT / DOWN word; the banners do.",
    engagement=f"Engagement per write: the points NPCs gave our posts (likes {ENG_POINTS['likes']}, reposts {ENG_POINTS['reposts']}, replies {ENG_POINTS['replies']}, follows {ENG_POINTS['follows']}) "
               f"for each write we spent, last {ENG_WINDOW_H} h. Base points: the Red multiplier is not in it, so the x2 on 26 Oct and the x4 on 1 Nov do not move it.\n"
               f"Views (capped at 500 a day), changes of mind and Blue are left out. Every write counts, reposts too: each one spends a slot of the team's {TEAM_CAP_PER_MIN} a minute.\n"
               f"Writes are those of the window ending {ENG_LAG_H} h earlier, because the portal books an hour's engagement about an hour late. "
               f"Most replies and likes arrive hours after the write (7 in 10 after 6 h), so the last day's writes are not finished paying; the figure is a rate, not a verdict on one change.\n"
               f"Green: {ENG_GREEN:g} or more · amber: {ENG_AMBER:g}-{ENG_GREEN:g} · red: under {ENG_AMBER:g} · grey: under {ENG_MIN_WRITES} writes or {ENG_MIN_LINES} portal lines. Goal {ENG_GOAL:g}, one point above the median of the first days at the cap.",)


# ---- drafting starved: the drafter found no model (23 Oct, 27,800 jobs lost as no_model in 3 h) ----
NOMODEL_SHORT_MIN, NOMODEL_LONG_MIN = 10, 30   # windows for no_model drops and live writes
NOMODEL_WRITES_FLOOR = 1.0                     # writes a minute over the short window: below it, drops make it red (normal ~2.9, 23 Oct starved ~0.4)
NOMODEL_NORMAL_WPM = 2.9                       # for the banner text only
BUDGET_LOW_X = 2                               # priced-model budget left under this many times the amplified-post reserve: amber


def drafting_state(actions, data, now):
    """The 'no model' banner: dict(level, text); green (empty text) when all is well or nothing can be read. Budget maths is swan_bot.llm's own; a missing file or import means no budget signal, not a crash."""
    short, long_ = (now - dt.timedelta(minutes=m) for m in (NOMODEL_SHORT_MIN, NOMODEL_LONG_MIN))
    drops = [(a["_t"], 1) for a in actions if a.get("act") in ("lost", "requeue") and a["_t"] >= long_
             and str(a.get("why")).split(":")[-1] == "no_model"]              # "no_model" and "expired:no_model"
    # 23 Oct: the bot logs a no-model spell as episode rows (act "no_model", "new" = attempts since the last row)
    drops += [(a["_t"], a["new"]) for a in actions if a.get("act") == "no_model" and a["_t"] >= long_
              and isinstance(a.get("new"), int) and not isinstance(a.get("new"), bool)]
    d10, d30 = sum(k for t, k in drops if t >= short), sum(k for _, k in drops)
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
            margin = reserve or 0.25 * llm.day_share(day)      # 31 Oct: no reserve (amplification off); still warn when low
            held, low = reserve > 0 and left <= reserve, left < BUDGET_LOW_X * margin
        except Exception:                      # no openai on this machine, odd file: show the drops only
            left = None
    gone = left is not None and left <= 0
    if not (d30 or held or low or gone):
        return dict(level="green", text="")
    level = "red" if gone or (d10 and wpm < NOMODEL_WRITES_FLOOR) else "amber"
    why = " · budget spent: paid models off" if gone else " · paid models held back for amplified posts" if held else ""
    head = "NO MODEL" if d30 else "BUDGET SPENT" if gone else "BUDGET LOW"
    text = f"{head} · {d10} drops in {NOMODEL_SHORT_MIN} min, {d30} in {NOMODEL_LONG_MIN} · {wpm:.1f} writes/min"
    summary = ("Replies stalled" if level == "red" else "Replies slowed") + (": no model free" if d30 else ": budget spent" if gone else ": budget low")
    detail = ([f"The drafter found no model free for {d30} drafts in the last {NOMODEL_LONG_MIN} min ({d10} in the last {NOMODEL_SHORT_MIN}); "
               "since 23 Oct they are put back, not dropped. "
               "Free models are parked or rate-limited; it retries after a pause."] if d30 else []) + \
        [f"Writing {wpm:.1f} a minute over the last {NOMODEL_SHORT_MIN} min (normal about {NOMODEL_NORMAL_WPM}; red below {NOMODEL_WRITES_FLOOR:g})."] + \
        ([f"${left:.2f} left today" + (": " + why[3:] if why else ": not the cause.")] if left is not None else []) + \
        ["Amber is slowed but working; red is stalled or out of budget."]
    return dict(level=level, text=text + (f" · ${left:.2f} left today" if left is not None else "") + why,
                summary=summary + (f" · {wpm:.1f} writes/min"), detail=detail)


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
    """Changes of mind in the portal's messages since `since`: toward / away / neither, primary or contribution. The
    message's head goes whatever it says (29 Oct: since the x2 of 26 Oct it reads "NPC engagement (×2 points): ", and
    the first item of every such line was being dropped)."""
    out = dict(toward=0, away=0, neither=0, primary_toward=0)
    for e in points:
        if e["_t"] < since:
            continue
        for part in re.split(r",| and ", (e.get("message") or "").partition(": ")[2]):
            m = MIND.match(part.strip())
            if not m or "mind" not in m.group(2):
                continue
            n, what = int(m.group(1)), m.group(2)
            side = ("toward" if "towards your side" in what else "away" if "away from your side" in what else
                    "neither" if "neither side" in what else None)       # no side named: an "other view" change
            if side is None:
                continue
            out[side] += n
            if side == "toward" and ("contribution" not in what or "primary" in what):     # a "primary contribution" is primary (_part)
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
    budget_now = (status.get("write_budget") or {}).get("limit") or TEAM_CAP_PER_MIN
    per_bucket = collections.Counter(int(a["_t"].timestamp() // CATCHUP_BUCKET_S) for a in actions
                                     if a.get("live") is True and a.get("act") in WRITES)
    first_bucket = int(min((a["_t"] for a in actions), default=now).timestamp() // CATCHUP_BUCKET_S) + 1
    starved = lambda made: (first_bucket <= int(made // CATCHUP_BUCKET_S) and per_bucket[int(made // CATCHUP_BUCKET_S)]
                            < VOLUME_AMBER * budget_now * CATCHUP_BUCKET_S / 60)
    catchup = dict(fresh=0, back=0)
    backlog = []
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
            bar, bucket, into = REACH_SPEED_RED, fresh, "fresh"
        elif a.get("act") == "reply_back":
            bar, bucket, into = REACH_BACK_MIN, back, "back"
        else:
            continue
        if into == "fresh" and lag > BACKLOG_MIN:
            backlog.append(lag)                 # the queue behind the new posts: its own row, never the light
            continue
        if lag > bar and starved(a["_t"].timestamp() - lag * 60):
            catchup[into] += 1                  # made while we were not posting: a backlog, not slowness
        else:
            bucket.append(lag)
    mf, mb = _median(fresh), _median(back)
    graded = lambda v, bar, red=None: ("grey" if v is None else "green" if v <= bar else "amber" if v <= (red or 3 * bar) else "red")
    left_out = lambda k: f" · {catchup[k]} catch-up left out" if catchup[k] else ""
    row("speed", "Reply time, new citizen posts", graded(mf, REACH_SPEED_MIN, REACH_SPEED_RED),
        (f"{mf:.1f} min (n {len(fresh)})" if mf is not None else "no new post answered this hour") + left_out("fresh"), f"≤ {REACH_SPEED_MIN} green · ≤ {REACH_SPEED_RED} amber · over red (min)",
        "Behind the citizen's session: check the LLM line under Bot.")
    row("speed", "Reply time, citizens answering us", graded(mb, REACH_BACK_MIN),
        (f"{mb:.1f} min" if mb is not None else "none this hour") + left_out("back"), f"≤ {REACH_BACK_MIN} min",
        "Reply-backs are slow: check Bot.")
    row("speed", "Backlog drained, last hour", "grey",
        f"{len(backlog)} replies to posts over {BACKLOG_MIN} min old (median {_median(backlog) / 60:.1f} h old)" if backlog else "none",
        f"not graded: posts older than {BACKLOG_MIN} min when we answered", "")
    for kind, name in (("fresh", "1st replies"), ("back", "2nd replies")):
        row("speed", f"Where the time goes, {name}", "grey", stage_line(stages[kind]), "wait + draft + hold",
            "Wait: their post to our pick (reading, queue). Draft: LLM calls and repairs. Hold: draft checked to sent "
            "(pacing, rate limit). Fills in from the first reply written after the deploy.")
    q = status.get("queue") or {}
    waiting = q.get("candidates", refreshes[-1].get("candidates") if refreshes else None)
    groups_q = sum((g or {}).get("queued") or 0 for g in ((refreshes[-1].get("groups") if refreshes else None) or {}).values())
    if waiting is not None:
        n_wait, per_h = max(waiting - groups_q, 0), len(fresh) + len(backlog) + catchup["fresh"]
        row("speed", "Citizens waiting now", "grey", f"{n_wait}" + (f" · about {n_wait / per_h:.0f} h to clear at {per_h} first replies an hour" if per_h else ""))

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
    hot = hot_roster(status)
    if hot:                    # hot mode (todo/45): one voice writes at a time on purpose, so the count is not graded against VOICES_MIN
        spares, lost = len(hot["spares"]), len(hot["lost"])
        row("accounts", "Hot voice", "red" if not hot["active"] else "amber" if not spares else "green",
            (f"@{hot['active']} writing" if hot["active"] else "none left: the bot is idle") + f" · {spares} standby · {lost} lost",
            "one live, at least one spare", "No hot voice left: name live ones in SWAN_HOT_VOICES and restart." if not hot["active"]
            else "Last hot voice: add spares to SWAN_HOT_VOICES before it goes.")
    elif voices is not None:
        row("accounts", "Voices in rotation", "amber" if voices < VOICES_MIN else "green", f"{voices}",
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
    row("volume", "Drafts passing first time", "grey",
        f"{share1:.0%}" if share1 is not None else "—", f"shown only (aim ≥ {REACH_SHARE:.0%}): a cost, not volume",
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
                volume=f"of {budget:g} a minute",
                conversion=f"toward / away today · {minds['neither']} neither")
    items = [dict(key=k, name=k.capitalize(), light=worst(k), head=heads[k], sub=subs[k], tip=LIGHT_TIPS[k], row=0,
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
        new = end["banned"] - prev["banned"]
        # the portal's counts row moves before the suspension messages do (23 Oct: 25 banned, 21 named): `unnamed` is
        # how many of the day's bans have no name and reason yet
        rows.append(dict(day=perth_span(d), date=d.isoformat(), today=d == today, registered=end["registered"],
                         banned=end["banned"], new_reg=end["registered"] - prev["registered"], new=new,
                         unnamed=max(new - len(why), 0),
                         why=" · ".join(f"{w} ×{why.count(w)}" for w in dict.fromkeys(why))))
        prev, d = end, d + dt.timedelta(days=1)
    listed = [dict(time=perth(x["_t"]).strftime("%a %H:%M"), username=x["username"], id=x["id"], why=x["why"])
              for x in sorted(sus, key=lambda x: x["_t"], reverse=True)]
    return rows[::-1], listed


# ---- one number for bans, hide rate with an interval, writes per ban, and the forecast (todo/42) ----
def ban_figures(log, accounts):
    """The bans number everywhere on the page: registered and banned from the newest account_log.counts row (it moves
    before the suspension messages that carry the names), `listed` = names the log holds, `lag` = bans not named yet.
    Falls back to the team page's table (portal.json "accounts") when there are no counts rows. None with neither."""
    rows = [c for c in (log or {}).get("counts") or [] if isinstance(c.get("registered"), int) and isinstance(c.get("banned"), int)]
    src = rows[-1] if rows else accounts if isinstance(accounts, dict) else {}
    if not isinstance(src.get("registered"), int) or not isinstance(src.get("banned"), int):
        return None
    listed = len({x.get("id") or x.get("username") for x in (log or {}).get("suspended") or []}) if rows else None
    lag = max(src["banned"] - listed, 0) if listed is not None else 0       # no activity log: nothing to compare with
    return dict(registered=src["registered"], banned=src["banned"], listed=listed, lag=lag, left=TOTAL_CAP - src["banned"],
                text=f"{src['banned']} banned" + (f" (list shows {listed})" if lag else ""))


def wilson(k, n, z=1.96):
    """(lo, hi) of the 95% Wilson score interval for k hits in n tries, or None for n = 0. Unlike the plain normal interval
    it stays inside [0, 1] and is not zero-width at k = 0 or k = n, which matters at a rate near 1%."""
    if n <= 0:
        return None
    k = min(max(k, 0), n)
    p, denom = k / n, 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (0.0 if k == 0 else max(0.0, centre - half)), (1.0 if k == n else min(1.0, centre + half))     # exact at the ends


def life_scan(path, since):
    """What the stealth rates need from logs/swan_actions.jsonl, in ONE streamed pass (the file is 100+ MB: never loaded
    whole, todo/34; lines are only parsed when their act is a write or a suspension). Our live writes only:
      day_writes   {Sydney day: live writes of any kind}   (the plan's unit: everything that spends the write budget)
      dead         {username: when the bot first got a 403 'suspended'} (late: it learns on its next action)
      text         {post id: (time, username)} text writes since `since` (replies, posts, threads; not reposts), for the hide rate and writes per ban
      slots        [time] of every live write since `since`, reposts included: each spent one of the team's 3 writes a minute (engagement per write)
    A missing file gives empty results."""
    out = dict(day_writes=collections.Counter(), dead={}, text={}, slots=[])
    try:
        f = open(path, "rb")
    except OSError:
        return out
    with f:
        for line in f:
            if not line.endswith(b"\n"):
                break                                    # being written
            i = line.find(b'"act": "', 0, 400)
            if i < 0 or line[i + 8:line.find(b'"', i + 8)] not in LIFE_ACTS:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            t = ts(r.get("ts")) if isinstance(r, dict) else None
            user = r.get("username") if t else None
            if not user:
                continue
            if r.get("act") == "suspended":
                out["dead"].setdefault(user, t)
                continue
            if r.get("live") is not True:                # dry runs, and the swarm's rows (no live flag)
                continue
            out["day_writes"][t.astimezone(SYDNEY).date().isoformat()] += 1
            if t >= since:
                out["slots"].append(t)
            pid = r.get("post_id")
            if r["act"] in TEXT_WRITES and pid not in (None, "None", ""):
                if t >= since:
                    out["text"][str(pid)] = (t, user)
    return out


HIDDEN_ALERT = re.compile(r"@(\w+): post #(\d+) hidden by the moderator")


def hidden_posts(logs):
    """{post id: username} of posts the moderator hid, from logs/swan_watch.jsonl (its hidden_post rows) and, for any the
    watch only alerted, logs/alerts.log. Empty when neither file is there."""
    out = {}
    for r in tail_jsonl(logs / "swan_watch.jsonl", 20_000_000):
        if r.get("act") == "hidden_post" and r.get("post_id") is not None:
            out[str(r["post_id"])] = r.get("username")
    for line in tail_lines(logs / "alerts.log", 5000):
        m = HIDDEN_ALERT.search(line)
        if m:
            out.setdefault(m.group(2), m.group(1))
    return out


def hide_rate(life, hidden, now):
    """Hidden text posts / text writes among writes made in the last HIDE_WINDOW_H hours that are at least HIDE_CENSOR_H
    old (a hide takes about 3.3 h to show, so younger writes would count as clean when they are only undecided), with the
    95% Wilson interval. Every hidden post is matched to a write in the window, so the top and bottom cover the same
    posts. {n, k, rate, lo, hi}; rate, lo and hi are None with no writes."""
    now_t = now - dt.timedelta(hours=HIDE_CENSOR_H)
    window = [pid for pid, (t, _) in life["text"].items() if now - dt.timedelta(hours=HIDE_WINDOW_H) <= t <= now_t]
    n, k = len(window), sum(pid in hidden for pid in window)
    iv = wilson(k, n)
    return dict(n=n, k=k, rate=k / n if n else None, lo=iv and iv[0], hi=iv and iv[1])


def writes_per_ban(life, log, now, hours):
    """Text writes ÷ bans over the last `hours`: {hours, writes, bans, wpb}; wpb is None with no bans. Writes are our live text
    writes in the action log (life_scan), bans the portal's count (bans_since: its counts move before its list of names)."""
    since = now - dt.timedelta(hours=hours)
    writes = sum(since <= t <= now for t, _ in life["text"].values())
    bans = bans_since(log, now, hours)
    return dict(hours=hours, writes=writes, bans=bans, wpb=writes / bans if bans else None)


def last_bans_hours(log, now, n=ROLL_MIN_BANS, cap=ROLL_MAX_H):
    """Hours back to the account_log counts row before the last `n` bans (so bans_since over them counts at least n), at
    most `cap`."""
    rows = sorted((ts(c["ts"]), c["banned"]) for c in (log or {}).get("counts") or []
                  if ts(c.get("ts")) and isinstance(c.get("banned"), int) and ts(c["ts"]) <= now)
    back = [t for t, b in rows if b <= rows[-1][1] - n] if rows else []
    return min(cap, (now - back[-1]).total_seconds() / 3600) if back else cap


def engagement_window(points, slots, end, hours=ENG_WINDOW_H):
    """Engagement per write over the `hours` before `end`: {hours, points, writes, lines, rate, parts}. points: base points
    of the NPC engagement the portal booked in those hours (likes, reposts, replies, follows less unfollows, at base: counts
    times ENG_POINTS, so the Red multiplier is not in it); writes: our live writes (slots, a list of times) in the window
    that ended ENG_LAG_H earlier; lines: how many portal lines fall in the window. rate is None with no writes. parts: the
    points per write by kind, replies / likes / the rest."""
    counts = collections.Counter()
    lines = 0
    for e in points:
        if end - dt.timedelta(hours=hours) < e["_t"] <= end:
            lines += 1
            c = parse_activity(e.get("message") or "")
            for k in ENG_POINTS:
                counts[k] += c.get(k, 0)
    shift = dt.timedelta(hours=ENG_LAG_H)
    writes = sum(end - dt.timedelta(hours=hours) - shift < t <= end - shift for t in slots)
    pts = {k: n * ENG_POINTS[k] for k, n in counts.items()}
    total = sum(pts.values())
    per = lambda v: v / writes if writes else None
    return dict(hours=hours, points=total, writes=writes, lines=lines, rate=per(total), counts=dict(counts),
                parts=dict(replies=per(pts.get("replies", 0)), likes=per(pts.get("likes", 0)),
                           rest=per(pts.get("reposts", 0) + pts.get("follows", 0) + pts.get("unfollows", 0))))


def engagement_figs(points, life, now):
    """The engagement-per-write figures for the tile: the headline window, the same window 24 h and 48 h earlier (to see
    the trend), the last 6 h, and what one more point per write is worth from now to the end of the budget at the
    multipliers in force. {now, d1, d2, h6, worth}."""
    slots = life.get("slots") or []
    end_day = dt.date.fromisoformat(str(_cfg("BUDGET_END_DAY", "2026-11-02")))
    today = now.astimezone(SYDNEY).date()
    cap_day, worth, d = TEAM_CAP_PER_MIN * 60 * 24, 0.0, today
    while d <= end_day:
        left = (sydney_midnight(d + dt.timedelta(days=1)) - now).total_seconds() / 86400 if d == today else 1.0
        worth += cap_day * min(1.0, max(0.0, left)) * next((m for md, m in reversed(MULTIPLIERS) if md <= d), 1)
        d += dt.timedelta(days=1)
    day = dt.timedelta(hours=24)
    return dict(now=engagement_window(points, slots, now), d1=engagement_window(points, slots, now - day),
                d2=engagement_window(points, slots, now - 2 * day), h6=engagement_window(points, slots, now, 6), worth=worth)


def hides_per_voice(hidden, banned_names):
    """Median hidden posts a banned voice had before it went (the watch stops looking once a voice is suspended, so
    these are lower bounds). None until there is a hidden post on record and at least 3 banned voices."""
    per = collections.Counter(u for u in hidden.values() if u)
    counts = [per.get(u, 0) for u in banned_names]
    if not hidden or len(counts) < 3:
        return None
    return dict(median=_median(counts), n=len(counts), with_hide=sum(c > 0 for c in counts))


def gap_trend(rows, now, ours, third):
    """How the gap to third place moved, from the hourly leaderboard series (data/leaderboard.jsonl lines {ts, score,
    third}). For 6 h and 24 h back: the gap then, the change in it (negative = closing), and what each side scored since.
    A window is left out when the series has no line near enough (within a quarter of the window, at least 1.5 h).
    {gap, windows: [...], points: lines in the series}."""
    pts = sorted((ts(r.get("ts")), r) for r in rows if ts(r.get("ts")) and _num(r.get("score")) is not None
                 and _num(r.get("third")) is not None)
    gap, windows = third - ours, []
    for hours in (6, 24):
        want = now - dt.timedelta(hours=hours)
        t, r = min(pts, key=lambda p: abs((p[0] - want).total_seconds()), default=(None, None))
        if t is None or abs((t - want).total_seconds()) > max(1.5, hours / 4) * 3600:
            continue
        then = r["third"] - r["score"]
        windows.append(dict(hours=hours, then=then, change=gap - then, us=ours - r["score"], them=third - r["third"]))
    return dict(gap=gap, windows=windows, points=len(pts))


PACE_HOURS = 24                                # the window of the leaderboard's points-an-hour column
PACE_MIN_HOURS = 6                             # until a line this old exists there is no pace to show
PACE_NOW_HOURS, PACE_NOW_MIN_HOURS, PACE_NOW_MAX_HOURS = 3, 2, 5    # the column beside it: who is speeding up or slowing down
                                                                    # (Marc, 29 Oct); no line 2-5 h back, no column
BOARD_TOP = 10                                 # the rest of the top ten folds under the last row shown (Marc, 29 Oct)


def team_pace(lines, rows, now, hours=PACE_HOURS, min_hours=PACE_MIN_HOURS, seen=None, max_hours=None):
    """Points an hour per team over the last `hours`, from the hourly all-teams series (data/team_scores.jsonl lines
    {ts, seen, scores: {team: score}}) and the board's current rows [{team, score}]. The site changes its scores once an
    hour, so time is counted from when the scores first showed (`seen` for the current rows, each line's own `seen`, or
    its `ts` for lines written before that field): dividing by the wall clock instead made the rate fall all hour
    between board changes and jump when one arrived. One reference line for everybody: the one nearest `hours` before
    `seen`, at least `min_hours` older than it (a shorter history gives the longest span it has) and, with `max_hours`, no
    older than that (so a gap in the series cannot turn a 3 h column into a 24 h one). A 24 h window
    spans a whole Sydney day, so the daily rhythm of citizens does not show as a change of pace; a 6 h one would, and a 6,000
    poll award inside it would look like 1,000 an hour. A team not in the reference line (new, or renamed) has no pace.
    Each step between lines is scaled to the Red multiplier in force at `end` (MULTIPLIERS, by the time it was earned:
    the portal books an hour that straddles a change at both): on 31 Oct 15:00 UTC the 24 h column was 22 h at x2 and 2 h
    at x4, half everyone's real rate (Marc, 31 Oct). The scale is applied to the whole change, Moderation points too.
    {span: hours the reference is back, window: `hours`, the column's label (the hourly lines rarely sit exactly `hours`
    back: 24.6 h showed as "25 h", Marc 1 Nov; per_hour divides by the real span), as_of: when the current scores showed,
    per_hour: {team: points an hour}, mult:
    the multiplier the pace is in, scaled: whether any of the window was earned at another} or None when no line is old
    enough."""
    end = seen or now
    dated = [(t, r) for t, r in ((ts(r.get("seen")) or ts(r.get("ts")), r) for r in lines)
             if t and isinstance(r.get("scores"), dict) and t < end]
    old = [(t, r) for t, r in dated if min_hours * 3600 <= (end - t).total_seconds() <= (max_hours or math.inf) * 3600]
    if not old:
        return None
    want = end - dt.timedelta(hours=hours)
    t, ref = min(old, key=lambda p: abs((p[0] - want).total_seconds()))
    span = (end - t).total_seconds() / 3600
    mult = multiplier_at(end)
    steps = sorted(((u, r["scores"]) for u, r in dated if u > t), key=lambda p: p[0])
    steps.append((end, {r["team"]: r["score"] for r in rows}))
    per_hour = {}
    for r in rows:
        prev_t, prev = t, _num(ref["scores"].get(r["team"]))
        if prev is None:
            continue
        total = 0.0
        for u, scores in steps:
            s = _num(scores.get(r["team"]))
            if s is None:
                continue                       # a line without the team: its change counts in the next step that has it
            total += (s - prev) * mult / mean_multiplier(prev_t, u)
            prev_t, prev = u, s
        per_hour[r["team"]] = round(total / span)
    return dict(span=span, window=hours, as_of=end, per_hour=per_hour, mult=mult, scaled=mean_multiplier(t, end) != mult)


def multiplier_at(t):
    """The Red multiplier in force at time t (MULTIPLIERS, by Sydney day)."""
    day = t.astimezone(SYDNEY).date()
    return next((m for d, m in reversed(MULTIPLIERS) if d <= day), 1)


def mean_multiplier(a, b):
    """The time-weighted Red multiplier over (a, b], split at Sydney midnights; multiplier_at(b) when b is not after a."""
    if b <= a:
        return multiplier_at(b)
    total, x = 0.0, a
    while x < b:
        nxt = min(b, sydney_midnight(x.astimezone(SYDNEY).date() + dt.timedelta(days=1)))
        total += multiplier_at(x) * (nxt - x).total_seconds()
        x = nxt
    return total / (b - a).total_seconds()


def sig3(x):
    """x to three significant figures (2,094 -> 2,090; 87 -> 87; None stays None): the leaderboard's pace columns, where
    four figures were hard to follow (Marc, 29 Oct)."""
    return x if not x else round(x, 2 - math.floor(math.log10(abs(x))))


def rate(x):
    """A pace as the leaderboard prints it, to three significant figures: 2.09k, 12.3k, 850, −40, and — for none."""
    if x is None:
        return "—"
    a = abs(sig3(x))
    s = f"{a / 1000:.{2 if a < 10_000 else 1 if a < 100_000 else 0}f}k" if a >= 1000 else f"{a:.0f}"
    return ("−" if x < 0 else "") + s


def signed(x):
    """+3 / −5 / 0 for a figure on the page (a real minus sign, as in 'net −5')."""
    v = round(x)
    return "0" if v == 0 else f"{'+' if v > 0 else '−'}{abs(v)}"


def bans_since(log, now, hours=24):
    """Bans in the last `hours`, from the account_log counts rows: the rise in banned since the last row at or before then
    (0 before the first row)."""
    rows = sorted((ts(c["ts"]), c["banned"]) for c in (log or {}).get("counts") or []
                  if ts(c.get("ts")) and isinstance(c.get("banned"), int) and ts(c["ts"]) <= now)
    before = [b for t, b in rows if t <= now - dt.timedelta(hours=hours)]
    return rows[-1][1] - (before[-1] if before else 0) if rows else 0


def _cfg(name, default):
    return getattr(bot_config, name, default)


def gap_words(x):
    """'6 over' / '3 under' / 'on target' for a gap to an aim, in words (a bare +6 did not say against what)."""
    v = round(x)
    return "on target" if v == 0 else f"{abs(v)} {'over' if v > 0 else 'under'}"


def ban_forecast(days, writes_by_day, roll, log, now):
    """The bans forecast against the plan (todo/39, todo/42), from account_days' rows, in the one account term: ACCOUNTS LEFT
    = not banned = alive + not yet registered = allowance - banned (Marc, 24 Oct). Per Sydney day from the first day on
    the portal to the end of the budget (config.BUDGET_END_DAY): planned writes (config.BAN_PLAN; a day not in it takes
    that day's actual writes if it is over, else the average of the last 3 complete days), forecast bans = planned / writes
    per ban, the actual, the net with its tolerance, then banned (cumulative), the path (config.BAN_PATH) and left at
    the end of the day: actual for past days, forecast for today and after. The forecast starts from the counts NOW with
    today's plan cut to the part of the day left, as swan_watch does, so the day's overshoot carries on. budget.py (pure)
    does the maths; None when it is not there or nothing can be planned. Today's net compares the bans so far with the
    forecast for the share of the day gone."""
    if budget is None or not days:
        return None
    today = now.astimezone(SYDNEY).date()
    end = dt.date.fromisoformat(str(_cfg("BUDGET_END_DAY", "2026-11-02")))
    goal, gday = _cfg("LEFT_GOAL", 60), str(_cfg("LEFT_DAY", "2026-10-31"))
    path = _cfg("BAN_PATH", {}) or {}
    by_date, first = {d["date"]: d for d in days}, dt.date.fromisoformat(days[-1]["date"])
    start, one = min(FORECAST_FROM, today), dt.timedelta(days=1)
    med = (roll or {}).get("wpb") if ((roll or {}).get("bans") or 0) >= ROLL_MIN_BANS else None     # roll: the last ROLL_MIN_BANS bans
    wpb = med or _cfg("WRITES_PER_BAN_DEFAULT", 145)
    recent = [writes_by_day[k] for k in sorted(writes_by_day) if k < today.isoformat() and writes_by_day[k] > 0][-3:]
    average = sum(recent) / len(recent) if recent else None
    plan_cfg, plan, src = _cfg("BAN_PLAN", {}) or {}, {}, {}
    d = start
    while d <= max(end, today):
        k = d.isoformat()
        value, how = ((plan_cfg[k], "plan") if k in plan_cfg else (writes_by_day.get(k), "actual") if d < today
                      else (average, "average"))
        if value:
            plan[k], src[k] = float(value), how
        d += one
    if not plan:
        return None
    for i in range((max(end, today) - start).days + 1):
        k = (start + i * one).isoformat()
        if k not in plan:                         # a day with nothing planned or known takes the last given value
            plan[k], src[k] = plan[max((p for p in plan if p < k), default=min(plan))], "carried"
    elapsed = min((now - sydney_midnight(today)).total_seconds() / 86400, 1.0)
    latest = by_date.get(today.isoformat())
    def at(day):                                  # (alive, spare) at the start of `day`, from the end of the day before
        row = by_date.get((day - one).isoformat())
        return (row["registered"] - row["banned"], TOTAL_CAP - row["registered"]) if row else (0, TOTAL_CAP)
    now_counts = (latest["registered"] - latest["banned"], TOTAL_CAP - latest["registered"]) if latest else at(today)
    try:
        rows = {}
        if start < today:
            rows.update({str(r["day"]): r for r in budget.forecast_days(plan, wpb, *at(start), start.isoformat(), (today - one).isoformat())})
        day_fc = {str(r["day"]): r for r in budget.forecast_days(plan, wpb, *at(today), today.isoformat(), max(end, today).isoformat())}
        rows.update(day_fc)                       # forecast bans a day, and today's net, from the day's start
        plan_now = dict(plan, **{today.isoformat(): plan[today.isoformat()] * max(1 - elapsed, 0.0)})
        ahead = {str(r["day"]): r for r in budget.forecast_days(plan_now, wpb, *now_counts, today.isoformat(), max(end, today).isoformat())}
        status = budget.reserve_status(list(ahead.values()), goal, gday)
    except (ValueError, KeyError, TypeError):
        return None
    out, d = [], first
    while d <= max(end, today):
        k, a, f = d.isoformat(), by_date.get(d.isoformat()), rows.get(d.isoformat())
        row = dict(date=k, day=perth_span(d), today=d == today, future=d > today, actual=a["new"] if a else None,
                   why=a["why"] if a else "", unnamed=a["unnamed"] if a else 0,
                   mult=next((m for md, m in reversed(MULTIPLIERS) if md <= d), 1), planned=None, src="", forecast=None,
                   net=None, tol=None, level="", banned=None, est=False, left=None, path=budget.ban_path(path, d),
                   over=None, goal_delta=None)
        if a and d < today:
            row.update(banned=a["banned"], left=TOTAL_CAP - a["banned"])
        elif d >= today and k in ahead:
            left = max(round(ahead[k]["left_end"]), 0)
            row.update(banned=TOTAL_CAP - left, left=left, est=True)
        if f:
            row.update(planned=f["planned_writes"], src=src.get(k, ""), forecast=f["forecast_bans"])
            if a and d <= today:
                due = f["forecast_bans"] * (elapsed if d == today else 1)
                row.update(net=a["new"] - due, tol=max(2, round(BAN_TOL_SIGMA * math.sqrt(due))))
                row["level"] = "down" if row["net"] > row["tol"] else "up" if row["net"] < -row["tol"] else ""
        if row["path"] is not None and row["banned"] is not None:
            row["over"] = row["banned"] - row["path"]
        if k == gday and d >= today and status.get("delta") is not None:
            row["goal_delta"] = status["delta"]
        out.append(row)
        d += one
    now_row = next((r for r in out if r["today"]), None)
    runway, prev, passed = None, float(sum(now_counts)), 0.0       # days from now until accounts left reaches 0 on the plan
    for k in sorted(ahead):
        frac = (1 - elapsed) if k == today.isoformat() else 1.0
        end_left = ahead[k]["left_end"]
        if end_left <= 0 and prev > 0:
            runway = passed + frac * prev / (prev - end_left)
            break
        prev, passed = end_left, passed + frac
    banned_now = latest["banned"] if latest else None
    left_now = TOTAL_CAP - banned_now if banned_now is not None else None
    per_day = (now_row["forecast"] if now_row else None)
    left_days = (sydney_midnight(end + one) - now).total_seconds() / 86400
    # steering: bans so far against the path, the path prorated from the start of the day to its end value tonight
    path_end = now_row["path"] if now_row else None
    start_banned = by_date[(today - one).isoformat()]["banned"] if (today - one).isoformat() in by_date else (
        banned_now - latest["new"] if latest else None)
    path_now = (start_banned + (path_end - start_banned) * elapsed
                if path_end is not None and start_banned is not None else None)
    over_now = banned_now - path_now if banned_now is not None and path_now is not None else None
    end_banned = now_row["banned"] if now_row and now_row["est"] else None      # forecast banned tonight: counts now + the rest of today's plan
    over_end = end_banned - path_end if end_banned is not None and path_end is not None else None
    try:
        alerts = budget.ban_alert(bans_since(log, now), per_day or 0, status, gday)
    except (ValueError, KeyError, TypeError):
        alerts = []
    ok = status.get("on_track")
    label = dt.date.fromisoformat(gday).strftime("%-d %b")
    summary = " · ".join(x for x in (
        f"bans today {now_row['actual']}" if now_row and now_row["actual"] is not None else None,
        f"forecast {now_row['forecast']:.0f}" if per_day is not None else None,
        f"net {signed(now_row['net'])}" if now_row and now_row["net"] is not None else None,
        f"left {left_now}" if left_now is not None else None,
        (f"{label}: {status['left_on_day']:.0f} left vs {goal:g} wanted ({signed(status['delta'])})" if ok is not None
         else f"{label} goal: day passed" if dt.date.fromisoformat(gday) < today else None)) if x)
    return dict(rows=out, summary=summary, alerts=alerts, wpb=wpb, wpb_src=f"last {roll['bans']} bans, {roll['hours']:.0f} h" if med else "default",
                goal=goal, goal_day=label, status=status, days_left=left_days, runway=runway, per_day=per_day,
                planned_today=now_row["planned"] if now_row else None, left_now=left_now, banned_now=banned_now,
                spare=TOTAL_CAP - latest["registered"] if latest else None, path_end=path_end, path_now=path_now, over_now=over_now,
                end_banned=end_banned, over_end=over_end)


def stealth_rates(logs, log, acct_days, now, points=()):
    """(rows for the hide, life and spare tiles, the ban_forecast dict or None, the hide-rate and Kaplan-Meier figures the
    tiles print): hide rate with its interval, hides per banned voice, writes per ban, runway, and the bans-against-plan line. "Hidden posts never colour stealth" (Marc, 23 Oct) holds for
    the count row; the hide RATE may colour it (a rate with an interval, 24 Oct). The rest is grey: the Pool line and the
    forecast alert carry the account-budget alarm."""
    life = life_scan(logs / "swan_actions.jsonl", now - dt.timedelta(hours=max(HIDE_WINDOW_H + 1, ROLL_MAX_H, 3 * ENG_WINDOW_H + ENG_LAG_H)))
    hidden = hidden_posts(logs)
    banned_at = dict(life["dead"])
    for x in (log or {}).get("suspended") or []:
        t = ts(x.get("ts"))
        if t and x.get("username"):
            banned_at[x["username"]] = min(t, banned_at.get(x["username"], t))
    grey = lambda name, text, target="", group="stealth": dict(group=group, name=name, light="grey", now=text, target=target, fix="", note="")
    rows = []
    hr = hide_rate(life, hidden, now)
    if hr["rate"] is None:
        rows.append(grey("Hide rate, last 24 h", "no text writes old enough yet", f"under {HIDE_TARGET:.1%}", "hide"))
    else:
        few = hr["n"] < HIDE_MIN_N
        light = "grey" if few else "green" if hr["hi"] < HIDE_TARGET else "red" if hr["lo"] > HIDE_TARGET else "amber"
        rows.append(dict(group="hide", name="Hide rate, last 24 h", light=light, note="",
                         now=f"{hr['rate']:.2%} [{hr['lo']:.2%}–{hr['hi']:.2%}] · {hr['k']} hidden of {hr['n']} text writes"
                         + (f" · n = {hr['n']}, under {HIDE_MIN_N}: too few to colour" if few else ""),
                         target=f"under {HIDE_TARGET:.1%} (green: the interval is below it · red: above)",
                         fix="Hidden posts per write are above target: the levers are in todo/40 and docs/06-strategy/hide-risk-analysis-2026-10-23.md."))
    hp = hides_per_voice(hidden, list(banned_at))
    if hp:
        rows.append(grey("Hides before a ban", f"median {hp['median']:g} per banned voice · {hp['with_hide']} of {hp['n']} had one",
                         "a lower bound: the watch stops once a voice is suspended", "hide"))
    rolls = {h: writes_per_ban(life, log, now, h) for h in (ROLL_HOURS, ROLL_LONG_H)}
    rolls["bans"] = last = writes_per_ban(life, log, now, last_bans_hours(log, now))
    forecast = ban_forecast(acct_days, life["day_writes"], last, log, now)
    few = last["bans"] < ROLL_MIN_BANS
    rows.append(grey(f"Last {ROLL_MIN_BANS} bans", f"{last['wpb']:.0f}" if last["wpb"] is not None else "no bans",
                     f"{last['writes']:,} writes ÷ {last['bans']} bans over {last['hours']:.0f} h"
                     + (f" · under {ROLL_MIN_BANS} bans in {ROLL_MAX_H // 24} days, plan uses {forecast['wpb']:.0f}" if few and forecast else ""), "life"))
    for h in (ROLL_HOURS, ROLL_LONG_H):
        r = rolls[h]
        rows.append(grey(f"Last {h} h", f"{r['wpb']:.0f}" if r["wpb"] is not None else "no bans", f"{r['writes']:,} writes ÷ {r['bans']} bans", "life"))
    if forecast:
        rows.append(grey("Time left", f"{forecast['days_left']:.1f} d", f"to the end of 2 Nov Sydney = {BUDGET_END_PERTH}", "left"))
        if forecast["per_day"] is not None:
            rows.append(grey("Plan today", f"{forecast['planned_today']:,.0f} writes ÷ {forecast['wpb']:.0f} = {forecast['per_day']:.1f} bans",
                             f"writes per ban from {forecast['wpb_src']}; writes are config.BAN_PLAN", "left"))
    if forecast and forecast["summary"]:
        rows.append(grey("Bans against the plan", forecast["summary"], "Bot > Accounts by day has the days to 2 Nov", "left"))
    return rows, forecast, dict(hide=hr, roll=rolls, eng=engagement_figs(points, life, now))


def plural(n, one, many=None):
    """'1 spare', '2 spares': the word for n."""
    return one if n == 1 else many or one + "s"


def hot_roster(status):
    """status.json["hot"] (hot mode, todo/45: one voice writes at a time, the others wait as spares) as
    {active, spares, lost}, or None when hot mode is off or the field is odd."""
    h = status.get("hot")
    if not isinstance(h, dict):
        return None
    names = lambda k: [x for x in h.get(k) or [] if isinstance(x, str)] if isinstance(h.get(k), list) else []
    return dict(active=h["active"] if isinstance(h.get("active"), str) else None, spares=names("spares"), lost=names("lost"))


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def pool_view(pool, now):
    """The Pool line (todo/38) from status.json["pool"], or None when the pool worker has not written one (as today).
    Red: state low, or runway_days under days_left. Amber: state sagging, or runway under RUNWAY_AMBER_X x days_left.
    Fields are read one by one; anything missing or odd is left out of the text and never turns a light by itself."""
    if not isinstance(pool, dict) or not pool:
        return None
    n = lambda k: _num(pool.get(k))
    fmt_pair = lambda a, b: f"{a:g}/{b:g}" if a is not None and b is not None else (f"{a:g}" if a is not None else "?")
    state = pool.get("state") if pool.get("state") in ("healthy", "sagging", "low") else None
    runway, left = n("runway_days"), n("days_left")
    lights, why = [], []
    if state:
        lights.append(dict(healthy="green", sagging="amber", low="red")[state])
        if state != "healthy":
            why.append(f"{lights[-1].upper()} state {state}: {fmt_pair(n('writers'), n('writers_target'))} writers")
    if runway is not None and left is not None:
        lights.append("red" if runway < left else "amber" if runway < RUNWAY_AMBER_X * left else "green")
        if lights[-1] != "green":
            why.append(f"{lights[-1].upper()} runway {runway:.1f} d of spare accounts against {left:.1f} d left"
                       + (f" (x{RUNWAY_AMBER_X:g} = {RUNWAY_AMBER_X * left:.1f} d is the amber bar)" if lights[-1] == "amber" else ""))
    order = {"red": 3, "amber": 2, "green": 1, "grey": 0}
    light = max(lights, key=order.get) if lights else "grey"
    fmt = fmt_pair
    writers = fmt(n("writers"), n("writers_target")) + " writers"
    extra = [f"{int(n(k))} {w}" for k, w in (("ramping", "ramp"), ("warming", "warm")) if n(k)]
    if extra:
        writers += f" (+{', '.join(extra)})"
    nxt = n("next_add_in_min")
    bits = [writers, fmt(n("alive"), n("alive_cap")) + " alive", fmt(n("total_used"), n("total_cap")) + " used"]
    runway_txt = (f"runway {runway:.1f}d" + (f" of {left:.1f}d" if left is not None else "")) if runway is not None else None
    sub = " · ".join(b for b in bits + [runway_txt,
                                        f"next +{nxt:.0f}m" if nxt is not None else None,
                                        f"{n('loss_per_day'):.1f} lost/day" if n("loss_per_day") is not None else None] if b)
    acts = []
    for a in (pool.get("last_actions") or [])[-POOL_ACTS:][::-1]:
        if isinstance(a, dict):
            t = ts(a.get("ts"))
            acts.append(dict(when=ago(now - t) if t else "?", act=short(str(a.get("act") or ""), 30), username=short(str(a.get("username") or ""), 30)))
    dry = pool.get("dry_run") is True
    head = f"Pool {state or '—'}" + (" · dry run" if dry else "")
    tip = ("Pool: how many voices are writing and how long the spare accounts last.\n"
           f"Red: state low, or runway under the days left. Amber: state sagging, or runway under {RUNWAY_AMBER_X:g}x the days left.\n"
           "Runway = spare registrations / accounts lost per day.")
    if why:
        tip += "\n\nNeeds a look:\n" + "\n".join(why)
    return dict(light=light, head=head, sub=sub, acts=acts, dry_run=dry, tip=tip)


def audit_rows(audit, now):
    """Rows for the stealth tile from data/pattern_audit.json (scripts/pattern_audit.py), [] when it is absent or has no
    score. The score row takes the audit's own grade; the worst metrics follow with theirs. Older than AUDIT_STALE_S: grey."""
    if not isinstance(audit, dict) or not isinstance(audit.get("metrics"), dict):
        return []
    t = ts(audit.get("ts"))
    stale = t is None or (now - t).total_seconds() > AUDIT_STALE_S
    ok = lambda g: g if g in ("green", "amber", "red") and not stale else "grey"
    score = _num(audit.get("stealth_score"))
    rows = [dict(group="stealth", name="Pattern score", light=ok(audit.get("grade")) if score is not None else "grey",
                 now=(f"{score:g}/100" if score is not None else "—") + (f" · {ago(now - t)} (stale)" if stale and t else " · stale" if stale else ""),
                 target="green 70+ · amber 45-69", note="",
                 fix="Our writes read like a rota: scripts/pattern_audit.py lists the worst metrics and voices (todo/38).")]
    for k in (audit.get("worst_metrics") or [])[:3]:
        m = audit["metrics"].get(k)
        if not isinstance(m, dict) or _num(m.get("value")) is None:
            continue
        th = m.get("thresholds") or {}
        lower = th.get("better") == "lower"
        rows.append(dict(group="stealth", name=f"Pattern: {short(str(m.get('label') or k), 60)}", light=ok(m.get("grade")),
                         now=f"{m['value']:g}", note="", fix=short(str(m.get("fix") or ""), 160),
                         target=(f"{'≤' if lower else '≥'} {th.get('green'):g} green · {'≤' if lower else '≥'} {th.get('red'):g} amber"
                                 if _num(th.get("green")) is not None and _num(th.get("red")) is not None else "")))
    offenders = [o for o in audit.get("worst_voices") or [] if isinstance(o, dict) and o.get("voice")][:3]
    if offenders:
        rows.append(dict(group="stealth", name="Worst voices", light="grey", target="", fix="", note="",
                         now=", ".join(f"{short(str(o['voice']), 24)} ({o.get('score')})" for o in offenders)))
    return rows


def cost_tiles(srows, bans, ban_no, forecast, figs, extra_rows, reach_rows, pool, status, now):
    """The tiles for what the writing costs us (Marc, 24 Oct), one account term throughout: ACCOUNTS LEFT = not banned =
    alive + not yet registered = 200 - banned. Rows of three: HIDE RATE -> WRITES PER BAN -> STEALTH (bans against the
    path), then ACCOUNTS (writing, standby, alive) and ACCOUNTS LEFT (against the goal on 31 Oct); Blue follows in
    blue_tile. Each is dict(key, name, head, sub, light, tip, rows, row). A dot carries the light, not the tile's fill. A
    dry-run pool never colours a tile."""
    order = {"red": 3, "amber": 2, "green": 1, "grey": 0}
    worst = lambda rows: max((r["light"] for r in rows), key=order.get, default="grey")
    by = lambda g: [r for r in extra_rows if r["group"] == g]
    hot = hot_roster(status)
    f = forecast or {}
    # ---- stealth: the bans forecast for tonight, against the path Marc steers by (25 Oct) ----
    over, path_now, path_end = f.get("over_end"), f.get("path_now"), f.get("path_end")
    end_banned = f.get("end_banned")
    if over is None:
        path_light = "grey"
    else:
        path_light = ("green" if over <= max(PATH_GREEN_MIN, PATH_GREEN_X * path_end) else
                      "amber" if over <= max(PATH_AMBER_MIN, PATH_AMBER_X * path_end) else "red")
    if over is not None:
        path_row = dict(group="stealth", name="Forecast against the path", light=path_light, note="",
                        now=f"{ban_no['text'] if ban_no else str(f['banned_now']) + ' banned'} · heading for {end_banned:.0f} by tonight, aim {path_end:.0f} ({gap_words(over)}) · "
                            f"right now the aim is {path_now:.0f} ({gap_words(f['over_now'])})",
                        target=f"within {max(PATH_GREEN_MIN, PATH_GREEN_X * path_end):.0f} green · {max(PATH_AMBER_MIN, PATH_AMBER_X * path_end):.0f} amber (config.BAN_PATH)",
                        fix="Forecast to lose accounts faster than the path allows: the levers are fewer writes a voice and a lower hide rate (todo/39, todo/40).")
        srows = [path_row] + srows
    stealth = dict(key="stealth", name="Stealth", rows=srows, tip=LIGHT_TIPS["stealth"], light=path_light,
                   head=f"{ban_no['banned']} banned" if ban_no else f"{bans} bans",
                   sub=f"{bans} today" + (f" · heading for {end_banned:.0f} by tonight (aim {path_end:.0f}: {gap_words(over)})" if over is not None
                                          else f" · forecast {f['per_day']:.0f} a day" if f.get("per_day") is not None else ""))
    # ---- hide rate ----
    hr = figs["hide"]
    hide_rows = by("hide")
    hide = dict(key="hide", name="Hide rate", rows=hide_rows, tip=LIGHT_TIPS["hide"], light=worst(hide_rows[:1]),
                head=f"{hr['rate']:.2%}" if hr["rate"] is not None else "—",
                sub=(f"target {HIDE_TARGET:.1%} · {hr['k']} of {hr['n']}" + (f" (n under {HIDE_MIN_N})" if hr["n"] < HIDE_MIN_N else "")) if hr["n"]
                else f"target {HIDE_TARGET:.1%} · no writes old enough")
    # ---- writes per ban ----
    rb = figs["roll"]["bans"]
    enough = rb["bans"] >= ROLL_MIN_BANS
    life_rows = by("life")
    life = dict(key="life", name="Writes per ban", rows=life_rows, tip=LIGHT_TIPS["life"], light="grey",
                head=f"{rb['wpb']:.0f}" if enough else "—",
                sub=f"last {rb['bans']} bans, over {rb['hours']:.0f} h" if enough
                else f"under {ROLL_MIN_BANS} bans in {ROLL_MAX_H // 24} days" + (f" · plan uses {f['wpb']:.0f}" if f else ""))
    # ---- accounts: how many are writing ----
    acc = status.get("accounts") or {}
    voices = acc.get("voices")
    p = pool if pool and not pool["dry_run"] else None
    pdict = status.get("pool") if isinstance(status.get("pool"), dict) else {}
    pn = lambda k: _num(pdict.get(k))
    banned = ban_no["banned"] if ban_no else None
    reg = ban_no["registered"] if ban_no else pn("total_used") if p else acc.get("used")
    alive = ban_no["registered"] - ban_no["banned"] if ban_no else acc.get("live")
    target = pn("writers_target")
    state_light = dict(healthy="green", sagging="amber", low="red").get(pdict.get("state")) if p else None
    a_rows = [r for r in reach_rows if r["group"] == "accounts"]
    if reg is not None:
        left_n = TOTAL_CAP - banned if banned is not None else None
        a_rows.append(dict(group="accounts", name="Accounts left = alive + not yet registered", light="grey", target="", fix="", note="",
                           now=(f"{left_n} left" if left_n is not None else "—")
                           + (f" = {alive} alive + {TOTAL_CAP - reg} not yet registered" if alive is not None else "")
                           + (f" · {ban_no['text']} of {TOTAL_CAP}" if ban_no else f" · {reg} registered of {TOTAL_CAP}")))
        a_rows.append(dict(group="accounts", name="Alive", light="grey", target="", fix="", note="",
                           now=(f"{alive} alive (max {LIVE_CAP})" if alive is not None else "—")
                           + (f" = {voices} writing + {acc.get('boosters')} {plural(acc.get('boosters') or 0, 'booster')}" if voices is not None and acc.get("boosters") is not None else "")))
    if state_light:
        a_rows.append(dict(group="accounts", name="Pool", light=state_light, target="healthy · sagging (amber) · low (red)", note="",
                           fix="The pool is short of writers: it registers and warms accounts on its own; check the pool actions below.",
                           now=f"{pdict.get('state')}: {target:g} writers wanted" if target is not None else str(pdict.get("state"))))
    acc_light = max([r["light"] for r in a_rows if r["group"] == "accounts" and r["now"] and r["light"] != "grey"] or ["grey"], key=order.get)
    standby = len(hot["spares"]) if hot else None
    accounts = dict(key="accounts", name="Accounts writing", rows=a_rows, tip=LIGHT_TIPS["accounts"], light=acc_light,
                    head=(f"{1 if hot['active'] else 0} writing" if hot else f"{voices} writing" if voices is not None else "—"),
                    sub=" · ".join(x for x in ((f"{standby} standby · {len(hot['lost'])} lost" if hot else
                                                f"of {target:g} wanted" if p and target is not None else None),
                                               f"{alive} alive" if alive is not None else None) if x))
    # ---- engagement per write: what each write we spend earns, against the goal (Marc, 25 Oct; replaces Accounts left) ----
    st, goal = f.get("status") or {}, f.get("goal")
    budget_rows = by("left")
    if st.get("delta") is not None:        # the account budget stays in the detail, grey: it no longer colours a tile
        budget_rows = [dict(group="left", name=f"Accounts left on {f['goal_day']}", light="grey", note="",
                            now=f"{st['left_on_day']:.0f} forecast against {goal:g} wanted ({signed(st['delta'])})",
                            target=f"{goal:g} or more; the path colours Stealth", fix="")] + budget_rows
    eng = engagement_tile(figs["eng"], budget_rows)
    for t, row in ((hide, 1), (life, 1), (stealth, 1), (accounts, 2), (eng, 2)):
        t["row"] = row
    return [hide, life, stealth, accounts, eng]


def engagement_tile(e, extra_rows=()):
    """The Engagement tile from engagement_figs: base points per write over the last 24 h, lit by ENG_GREEN / ENG_AMBER
    (grey when the window is thin), with the split by kind, the two days before, the last 6 h and what one more point per
    write is worth to the end. extra_rows: the account-budget rows (Time left, Plan today, Bans against the plan) that
    used to sit under Accounts left; they stay in the detail, grey."""
    n, d1, d2, h6 = e["now"], e["d1"], e["d2"], e["h6"]
    thin = n["rate"] is None or n["writes"] < ENG_MIN_WRITES or n["lines"] < ENG_MIN_LINES
    light = "grey" if thin else "green" if n["rate"] >= ENG_GREEN else "amber" if n["rate"] >= ENG_AMBER else "red"
    fmt = lambda w: f"{w['rate']:.2f}" if w["rate"] is not None else "—"
    grey = lambda name, now, target="": dict(group="left", name=name, light="grey", now=now, target=target, fix="", note="")
    rows = [dict(group="left", name=f"Engagement per write, last {ENG_WINDOW_H} h", light=light, note="",
                 now=(f"{fmt(n)} = {n['points']:,.0f} points ÷ {n['writes']:,} writes" if n["rate"] is not None else "no writes in the window")
                 + (f" · thin: {n['lines']} portal lines, {n['writes']} writes" if thin and n["rate"] is not None else ""),
                 target=f"green {ENG_GREEN:g}+ · amber {ENG_AMBER:g}+ · red below · goal {ENG_GOAL:g}",
                 fix="Engagement per write is under the 24 h baseline: the levers and what each is worth are in "
                     "docs/06-strategy/engagement-audit-2026-10-25.md (fresh targets first, no wasted slots, reply-backs, news threads).")]
    if n["rate"] is not None:
        p = n["parts"]
        rows.append(grey("Where it comes from", f"citizen replies {p['replies']:.2f} · likes {p['likes']:.2f} · reposts and follows {p['rest']:.2f} per write",
                         f"{n['counts'].get('replies', 0)} replies and {n['counts'].get('likes', 0)} likes in {n['hours']} h = "
                         f"{100 * n['counts'].get('replies', 0) / n['writes']:.0f} replies per 100 writes"))
    rows.append(grey("The days before", f"{fmt(d1)} a day ago · {fmt(d2)} two days ago · {fmt(h6)} in the last 6 h",
                     "the last 6 h swing with the time of day (Sydney afternoon is best, night worst); judge by the 24 h figure"))
    rows.append(grey("One more point per write is worth", f"≈ {e['worth']:,.0f} points to the end at the multipliers in force",
                     "writes at the team cap of 3 a minute, x2 from 26 Oct and x4 from 1 Nov (derived, not confirmed)"))
    return dict(key="engagement", name="Engagement per write", rows=rows + list(extra_rows), tip=LIGHT_TIPS["engagement"], light=light,
                head=fmt(n), sub=f"points per write, 24 h · goal {ENG_GOAL:g}")


def blue_tile(blue):
    """The Blue tile (Marc, 24 Oct): pending slots filled out of the cap, the number to keep full, with the reports ruled
    successful and failed since 9pm beside it. Light: fill (BLUE_FILL_GREEN / BLUE_FILL_AMBER); a 6 h lock caps it at amber
    (the slots cannot refill), a silent swan-blue is red. Grey when swan-blue has no status. Not counted in the page word."""
    tip = LIGHT_TIPS["blue"]
    if not blue or blue.get("pending") is None or not blue.get("cap"):
        row = dict(group="blue", name="Pending slots", light="grey", now="swan-blue has not written a status", target="", fix="", note="")
        return dict(key="blue", name="Blue", head="—", sub="not running", light="grey", tip=tip.format(cap=30), rows=[row], row=2, fill=None)
    cap = blue["cap"]
    pend, head, extra = blue_pending(blue["pending"], cap)
    fill = pend / cap
    light = "green" if fill >= BLUE_FILL_GREEN else "amber" if fill >= BLUE_FILL_AMBER else "red"
    why = f"{pend} of {cap} slots filled" + (f"; {blue_ledger_note(extra)}" if extra else "")
    if blue["locked"]:             # a 6 h lock after a "genuine" ruling: nothing to act on, so the dot is grey (Marc, 24 Oct)
        light, why = "grey", f"{why}; locked until {blue['locked']}"
    if blue["stale"]:
        light, why = "red", f"no status for {blue['ago'].replace(' ago', '')}"
    c = blue["counts"]
    row = dict(group="blue", name="Pending slots", light=light, now=why, target=f"{BLUE_FILL_GREEN:.0%}+ full", note="",
               fix="Slots are empty: " + ("locked, they refill when the lock ends." if blue["locked"] else
                                          f"{blue['ready']} reports ready; see Blue below for why the rest are not filed."))
    return dict(key="blue", name="Blue reports", light=light, tip=tip.format(cap=cap), rows=[row], row=2, fill=fill,
                head=head,
                sub=f"{c['success']} successful · {c['failed']} failed" + (f" · +{extra} ruled early" if extra else "") +
                    (f" · locked until {blue['locked']}" if blue["locked"] else ""))


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
    lock_t = final_time(root)
    lock = (read_json(data / "portal_lockout.json") or None) if lock_t else None
    if lock_t:                                 # final mode: every tile as it was at the lockout; the count has its own (final_board).
        # By the lines the lockout snapshot had, not by time: the portal's log lags its board by an hour or more, so a
        # line stamped before the lockout can arrive after it (2 Nov: at 07:47 the newest line was still 05:46).
        seen_lines = {(e.get("ts"), e.get("points"), e.get("message")) for e in (lock or {}).get("events") or []}
        late = [e for e in points if (e.get("ts"), e.get("points"), e.get("message")) not in seen_lines]
        points = [e for e in points if (e.get("ts"), e.get("points"), e.get("message")) in seen_lines]
    else:
        late = []
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

    log = portal.get("account_log")
    acct_days, banned_list = account_days(log, now)
    ban_no = ban_figures(log, portal.get("accounts"))      #the one bans number: Bot header, Accounts, Stealth tile

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
        blue_banner = dict(level="green", text=f"locked until {blue['locked']}" + (f" · {blue_pending(blue['pending'], blue['cap'] or blue['pending'])[1]}" if blue["pending"] else ""))   # a lock is shown on the Blue tile, not as an alert (Marc, 24 Oct)
    else:
        blue_banner = dict(level="green", text="running" + (f" · {blue_pending(blue['pending'], blue['cap'] or blue['pending'])[1]}" if blue["pending"] else ""))

    draft_banner = drafting_state(actions, data, now)
    final = final_time(root) is not None
    if final:                                  # competition over: the stopped services are not an incident
        banner = dict(level="green", text=f"competition over · bot stopped {hm_day(final_time(root), now)} Perth")
        blue_banner = dict(level="green", text="stopped")
        draft_banner = dict(draft_banner, level="green")

    # ---- score (typed in by hand: scripts/score.sh) ----
    entries = [e for e in (read_json(data / "score.json") or []) if ts(e.get("ts")) and not (lock_t and ts(e["ts"]) > lock_t)]
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
    fin = None
    if lock:
        fin = final_board(lock, tail_jsonl(data / "team_scores.jsonl", 400_000), portal, late,
                          read_json(data / team_sides.SIDES_FILE) or {}, read_json(data / "portal_award_board.json"))
        after = fin["state"] == "final" or fin["played"]      # the board has moved since the lockout
        # Until the referendum lands the board stays the lockout's (ranks and scores as at the stop) and the last hour of
        # play is only added beside it (Marc, 2 Nov: "only the final hour points is the new element")
        board_src, pace_src = (portal if fin["state"] == "final" else lock), fin["end_board"]
    else:
        board_src = pace_src = portal
    board = dict(leader=board_src.get("leader"), above=board_src.get("above"), below=board_src.get("below"),
                 rank=board_src.get("rank"), score=board_src.get("score"),
                 **leaderboard_rows(board_src)) if board_src.get("rank") else None
    if board:
        board["trend"] = None
    if board and board["cutoff"] is not None:      # behind 3rd: is the gap closing? (data/leaderboard.jsonl, hourly, from the portal poll)
        third = next(r for r in board["finalists"] if r["rank"] == 3)
        board["trend"] = None if fin else gap_trend(tail_jsonl(data / "leaderboard.jsonl", 500_000), now, board["score"], third["score"])
    if board:                                  # every team's points an hour (data/team_scores.jsonl, ~5 KB a line: 400 KB is about 3 days),
        lines, seen = tail_jsonl(data / "team_scores.jsonl", 400_000), ts(pace_src.get("scores_ts"))    # over a day and the last 3 h
        for key, hours, least, most in (("pace", PACE_HOURS, PACE_MIN_HOURS, None),
                                        ("pace_now", PACE_NOW_HOURS, PACE_NOW_MIN_HOURS, PACE_NOW_MAX_HOURS)):
            board[key] = team_pace(lines, pace_src.get("rows") or [], now, hours=hours, min_hours=least, seen=seen, max_hours=most)
            if board[key]:
                board[key]["as_of_label"] = hm(board[key]["as_of"])
    if board:                                  # Yes / No / ? after each name (data/team_sides.json, from the polls' awards: swan_dash/sides.py)
        state = read_json(data / team_sides.SIDES_FILE) or {}
        rows_all = board_src.get("rows") or []
        shown = {r["rank"] for r in board["finalists"] + board["near"]}
        board["fourth"] = next((dict(r) for r in rows_all if r["rank"] == 4 and r["rank"] not in shown), None) if board["rank"] <= 3 else None
        last = max(shown | {board["fourth"]["rank"] if board["fourth"] else 0})
        board["rest"] = [dict(r) for r in rows_all if last < r["rank"] <= BOARD_TOP]
        for r in board["finalists"] + board["near"] + board["between"] + ([board["fourth"]] if board["fourth"] else []) + board["rest"]:
            name = TEAM_NAME if r.get("us") else r["team"]
            r["side"] = team_sides.label(team_sides.side_of(state, name))
            if fin and after:                      # since the lockout: last hour of play, referendum gain
                was = fin["was_rank"].get(name)
                r.update(was_rank=was, was_score=fin["was_score"].get(name),
                         gain=fin["gain"].get(name), play=fin["play"].get(name), approx=name in fin["approx"])
            for key in ("pace", "pace_now"):   # red / green against ours on the figures as printed (3 significant figures)
                of = (board[key] or {}).get("per_hour") or {}
                r[key], ours = sig3(of.get(name)), sig3(of.get(TEAM_NAME))
                r[key + "_vs_us"] = None if r[key] is None or ours is None or r.get("us") else r[key] - ours
    if fin:                                    # the Final line, the Score / Rank tiles and the Referendum block
        if board:
            board["final"] = fin["state"] == "final"
            board["after"] = after
            board["combined"] = fin["combined"]
        us_was, us_score = fin["was_rank"].get(TEAM_NAME), fin["was_score"].get(TEAM_NAME)
        fin.update(stopped=hm_day(lock_t, now), us_was=us_was, us_was_score=us_score,
                   rank=portal.get("rank") if fin["state"] == "final" else us_was,
                   score=portal.get("score") if fin["state"] == "final" else us_score,
                   posted=hm(ts(portal.get("scores_ts"))) if after and ts(portal.get("scores_ts")) else None,
                   us_gain=fin["gain"].get(TEAM_NAME), us_play=fin["play"].get(TEAM_NAME),
                   teams=portal.get("teams") or fin["teams"])
        rows_now = sorted(portal.get("rows") or [], key=lambda r: r["rank"])
        if fin["state"] == "final" and len(rows_now) > 1:      # the margin: over #2 when first, else behind #1
            top, second = rows_now[0], rows_now[1]
            fin["lead"] = (dict(points=top["score"] - second["score"], other=second["team"], ahead=True) if top["team"] == TEAM_NAME
                           else dict(points=top["score"] - (fin["score"] or 0), other=top["team"], ahead=False))
        if fin["state"] == "final":
            side = (fin["winner"] or "").upper()
            fin["text"] = ((f"Kingstonia voted {side}: " + ("our side won" if fin["winner"] == team_sides.OUR_SIDE else "the other side won")
                            if side else "referendum counted")
                           + f" · Operation Swan finished #{fin['rank']} of {fin['teams']}"
                           + (f" (#{us_was} at {hm(lock_t)})" if us_was else ""))
        elif fin["played"]:
            fin["text"] = (f"competition over at {hm(lock_t)} Perth · last hour of play posted {fin['posted']}"
                           + (f" ({fin['us_play']:+,})" if fin["us_play"] is not None else "")
                           + " · referendum count under way")
        else:
            fin["text"] = f"competition over at {hm(lock_t)} Perth · referendum count under way, final scores to come"
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
                rows.append(dict(t=ts(t), who="", what="deploy", text=" ".join(subject.split()),
                                 kind="event", family="ops"))
            elif "hidden by the moderator" in msg:          # deploy/healthcheck + swan-watch: a voice lost a post
                rows.append(hidden_row(ts(t), msg))
            else:                                           # each alert kind its own colour (Marc, 22 Oct)
                what, kind = next(((w, k) for rx, w, k in ALERT_KINDS if re.match(rx, msg)), ("alert", "event"))
                rows.append(dict(t=ts(t), who="", what=what, text=" ".join(msg.split()), kind=kind))   # the template clips it
    rows = collapse(rows)
    rows.sort(key=lambda r: r.get("last") or r["t"], reverse=True)   # a conversation moves up when it gets more
    for r in rows:
        r.setdefault("time", hm(r["t"]))
        r.setdefault("post", None)
        r.setdefault("detail", None)
    items = bundle(rows)

    # ---- the trending pulse the bot writes towards (todo/15): its newest "pulse" record ----
    p = next((a for a in reversed(actions) if a.get("act") == "pulse"), None)
    pulse = p and dict(id=p.get("id"), ago=ago(now - p["_t"]),
                       stale=(now - p["_t"]).total_seconds() > PULSE_MAX_AGE_S,
                       hooks=[short(h.get("text")) for h in p.get("hooks") or [] if isinstance(h, dict)],
                       no_shapes=[short(x) for x in p.get("no_shapes") or []],
                       yes_lines=[short(x) for x in p.get("yes_lines") or []],
                       avoid=[short(x) for x in p.get("avoid") or []],
                       worries=[short(x) for x in p.get("worries") or []],        # todo/52 WS6: from the citizens' posts
                       rising=[short(x) for x in p.get("rising") or []], citizens=p.get("citizens") or 0)

    every = tail_jsonl(logs / "deploys.jsonl", 200_000)
    deploys = [d for d in every if d.get("result") == "ok"]
    running = dict(sha=deploys[-1]["new"][:7], prev=deploys[-1]["old"][:7], when=hm_day(ts(deploys[-1]["ts"]), now),
                   light="green" if every[-1] is deploys[-1] else "red",
                   failed=hm_day(ts(every[-1]["ts"]), now) if every[-1] is not deploys[-1] else None) if deploys else None

    rc = reach(actions, status, points, now, day_start, read_json(data / "reach_notes.json") or {})
    today_acct = next((d for d in acct_days if d["today"]), None)
    bans = today_acct["new"] if today_acct else 0
    hidden_today = sum(1 for r in rows if r.get("kind") == "hidden" and r["t"] >= day_start)
    srows = [dict(group="stealth", name="New bans today", light="grey",
                  now=f"{bans}" + (f" · {today_acct['why']}" if today_acct and today_acct["why"] else ""),
                  target="shown only: the path colours Stealth", fix="", note=""),
             dict(group="stealth", name="Posts hidden today", light="green", now=f"{hidden_today}",
                  target="shown only: hidden posts already show up as bans", fix="", note=""),
             dict(group="stealth", name="Banned in total", light="grey",
                  now=f"{ban_no['text']} of {ban_no['registered']} registered" if ban_no else "—", target="the portal's count; names follow it", fix="", note="")]
    extra_rows, forecast, figs = stealth_rates(logs, log, acct_days, now, points)       # todo/42: rates, writes per ban, runway, the plan
    pattern = audit_rows(read_json(data / "pattern_audit.json"), now)      # todo/38: how much our writes read like a rota; [] until the audit has run
    for r in pattern:      # shown, never graded (Marc, 24 Oct: bans, hide rate and writes per ban are the stealth numbers)
        r["target"] = (r["target"] + " · " if r.get("target") else "") + f"graded {r['light']}, not counted in the tile"
        r["light"] = "grey"
    srows += pattern
    pool = pool_view(status.get("pool"), now)          # todo/38: None until the pool worker writes status.json["pool"]
    tiles = cost_tiles(srows, bans, ban_no, forecast, figs, extra_rows, rc["rows"], pool, status, now)
    rc["lights"] += tiles
    rc["lights"].append(blue_tile(blue))
    seen = {id(r) for r in rc["rows"]}
    new_rows = [r for t in tiles for r in t["rows"] if id(r) not in seen] + [r for r in extra_rows if id(r) not in seen]
    rc["rows"] += list({id(r): r for r in new_rows}.values())
    rc["fixes"] += [r for r in rc["rows"] if r["light"] in ("amber", "red") and r not in rc["fixes"]]
    order = {"red": 3, "amber": 2, "green": 1, "grey": 0}
    for i in rc["lights"]:      # the hover: the rule, then the amber and red rows with their figure and any note (Marc, 23 Oct)
        bad = [f"{r['light'].upper()} {r['name']}: {r['now']}" + (f" (in hand: {r['note']})" if r.get("note") else "")
               for r in i["rows"] if r["light"] in ("amber", "red")]
        i["tip"] = i["tip"] + ("\n\nNeeds a look:\n" + "\n".join(bad) if bad else "\n\nNothing amber or red.")
        if i["key"] == "speed":
            split = [f"{r['name'].removeprefix('Where the time goes, ')}: {r['now']}" for r in i["rows"] if r["name"].startswith("Where the time goes")]
            i["tip"] += "\n\nWhere the time goes (median minutes):\n" + "\n".join(split)
    rc["light"] = max((i["light"] for i in rc["lights"] if i["key"] != "blue"), key=order.get)    # slots are an aim, not an incident
    levels = (banner["level"], blue_banner["level"], draft_banner["level"])      # the page word is the bot's health; red tiles are performance (Marc, 24 Oct)
    return dict(
        pool=pool, hot=hot_roster(status),
        now=hm(now), banner=banner, blue_banner=blue_banner, draft_banner=draft_banner, acct_days=acct_days, banned_list=banned_list,
        bans=ban_no, forecast=forecast,
        worst="red" if "red" in levels else "amber" if "amber" in levels else "green",
        fin=fin, status_word="FINAL" if final else STATUS_WORD["red" if "red" in levels else "amber" if "amber" in levels else "green"], final=final, score=score, history=history, board=board, milestone=milestone,
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
        activity=items[:ACTIVITY_TOP], older=older_critical(items[ACTIVITY_TOP:]), running=running, pulse=pulse, facts=facts,
        blue=blue, reach=rc,
        rollback=ROLLBACK.format(prev=running["prev"]) if running and banner["level"] == "red" else None,
        built=perth(now).strftime("%H:%M:%S"))


def render(ctx, template="index.html.j2"):
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(pathlib.Path(__file__).parent / "templates"),
                             autoescape=True, undefined=jinja2.StrictUndefined, trim_blocks=True, lstrip_blocks=True)
    env.filters["n"] = lambda x: "—" if x is None else f"{x:,}"
    env.filters["rate"] = rate
    env.filters["short"], env.filters["hm"], env.filters["signed"], env.filters["pl"] = short, hm, signed, plural
    return env.get_template(template).render(ctx)


def write_atomic(path, text):
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


REF_MIN_STEP = 15_000          # one board step this big for any team after the lockout is the referendum award (20,000 at least;
                               # an hour of play at ×4 was ~7,000 for the leaders)
PLAY_LINES = ("NPC engagement", "Moderation")   # points-log lines of play; any other line after the lockout is the referendum


def final_board(lock, lines, portal, late, sides, award_board=None):
    """Final mode: what the referendum count did to the board, against the lockout board (data/portal_lockout.json, saved
    at the stop). The scores move twice after the lockout: the last hour of play (the portal posts it at ~:19) and the
    referendum award (winning side only). The first board step where a team gains REF_MIN_STEP or more is the award and
    the board before it is the end of play; when both land in one step the gain is everything after the lockout
    (`combined`), except ours, which our own points-log lines split exactly. `lines`: data/team_scores.jsonl;
    `late`: our points-log lines after the lockout. state 'counting' until the award shows; `played` once the last hour
    of play has moved the board (Marc, 2 Nov: show it while the count goes on), with `play` the gain since the lockout.
    The portal posts the award on its own and keeps scoring engagement after it, so the award is the step alone. The
    hourly series can miss the board between the two (2 Nov: award 08:10, read 08:15, next play 08:30, next hourly line
    09:00): `award_board` {seen, scores} is that board, saved by hand and maybe partial. Without it a team on the losing
    side has no award (0) and a winner's is its change since the end of play, marked approximate (`approx`)."""
    lock_rows = lock.get("rows") or []
    lock_scores = {r["team"]: r["score"] for r in lock_rows}
    seen = ts(lock.get("scores_ts"))
    boards = [((ts(r.get("seen")) or ts(r.get("ts"))), r["scores"]) for r in lines if isinstance(r.get("scores"), dict)
              and seen and (ts(r.get("seen")) or ts(r.get("ts")) or seen) > seen]
    boards.append((ts(portal.get("scores_ts")), {r["team"]: r["score"] for r in portal.get("rows") or []}))
    partial = None
    if award_board and ts(award_board.get("seen")) and award_board.get("scores"):
        partial = award_board["scores"]
        boards = sorted(boards + [(ts(award_board["seen"]), partial)], key=lambda tb: tb[0] or seen)
    prev = end_play = lock_scores
    end_seen, step = seen, None
    for t, b in boards:
        if b == prev:
            continue
        if max((v - prev[k] for k, v in b.items() if k in prev), default=0) >= REF_MIN_STEP:
            step = b
            break
        if b is partial:                       # a partial board can only be the award step
            continue
        end_play = prev = b
        end_seen = t or end_seen
    ours = [e for e in late if not (e.get("message") or "").startswith(PLAY_LINES)]
    award = sum(e["points"] for e in ours)
    out = dict(state="counting" if step is None else "final", award=award if ours else None,
               notes=[dict(time=hm(e["_t"]), points=e["points"], text=e.get("message") or "") for e in ours],
               was_rank={r["team"]: r["rank"] for r in lock_rows}, was_score=lock_scores,
               teams=len(lock_rows) or None, winner=None, gain={}, play={}, combined=False, approx=set(),
               played=end_play is not lock_scores,
               # the board less the award, for the 24 h / 3 h rates (Marc, 2 Nov: the last hour of play goes into them)
               end_board=dict(scores_ts=end_seen.isoformat() if end_seen else None,
                              rows=[dict(team=t, score=v) for t, v in end_play.items()]))
    if step is None:
        out["play"] = {t: v - lock_scores[t] for t, v in end_play.items() if t in lock_scores}
        return out
    final_t, final = boards[-1]
    combined = end_play is lock_scores
    step_gain = {t: v - end_play[t] for t, v in step.items() if t in end_play}    # the award step alone
    if ours and award > 0:                     # the award goes to the winning side only, and we know ours
        winner = team_sides.OUR_SIDE
    else:
        votes = collections.Counter(team_sides.side_of(sides, t) for t, g in step_gain.items() if g >= REF_MIN_STEP)
        votes.pop(None, None)
        winner = votes.most_common(1)[0][0] if votes else None
    gain, approx = {}, set()
    for t, v in final.items():
        if t not in end_play:
            continue
        if t in step_gain:
            gain[t] = step_gain[t]
        elif winner and team_sides.side_of(sides, t) not in (None, winner):
            gain[t] = 0                        # the losing side gets no award: all its change is play
        else:
            gain[t] = v - end_play[t]
            approx.add(t)
    if ours:                                   # our own points-log line is exact
        gain[TEAM_NAME] = award
        approx.discard(TEAM_NAME)
    play = {t: final[t] - lock_scores[t] - gain[t] for t in gain if t in lock_scores}
    out["end_board"] = dict(scores_ts=final_t.isoformat() if final_t else None,      # every play point, for the rates
                            rows=[dict(team=t, score=v - gain.get(t, 0)) for t, v in final.items()])
    out.update(gain=gain, play=play, combined=combined, winner=winner, approx=approx)
    return out


def final_time(root):
    """The lockout time when FINAL is there: its content (ISO time) or else its mtime; None while the competition runs.
    The page is then built as of that moment, so every rolling window shows what it showed at the stop."""
    path = root / FINAL_FILE
    if not path.is_file():
        return None
    return ts(path.read_text().strip()) or dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=pathlib.Path, required=True, help="directory nginx serves")
    ap.add_argument("--root", type=pathlib.Path, default=ROOT, help="repo checkout with logs/ and data/")
    args = ap.parse_args()
    now = final_time(args.root) or dt.datetime.now(dt.timezone.utc)
    html = render(gather(args.root, now, service_state()))
    args.out.mkdir(parents=True, exist_ok=True)
    write_atomic(args.out / "index.html", html)
    (args.out / "lab.html").unlink(missing_ok=True)      # the NPC lab page, retired 2026-10-23 (todo/33)
    write_atomic(args.out / "robots.txt", "User-agent: *\nDisallow: /\n")
    write_atomic(args.out / "app.js", (pathlib.Path(__file__).parent / "templates" / "app.js").read_text())


if __name__ == "__main__":
    main()
