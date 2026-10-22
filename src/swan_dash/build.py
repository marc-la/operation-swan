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
from swan_dash.lab import gather_lab

ROOT = pathlib.Path(__file__).resolve().parents[2]
PERTH = ZoneInfo("Australia/Perth")
SYDNEY = ZoneInfo("Australia/Sydney")          # competition days roll over at midnight Sydney (9pm Perth)
QUOTA_DAY = ZoneInfo("America/Los_Angeles")    # data/llm_usage.json days (swan_bot/llm.py): free quotas reset there
TEAM_CAP_PER_MIN = 3                           # posts + replies + reposts, team-wide (rules)
LIVE_CAP, TOTAL_CAP = 50, 200                  # accounts alive at once / ever
WRITES = {"post": "post", "reply": "reply", "second_voice": "2nd voice", "reply_back": "reply-back",
          "journalist": "journalist", "thread": "own thread", "thread_answer": "thread answer", "repost": "repost"}
# poll awards and Red multiplier changes, as Sydney calendar dates (docs/01-competition/schedule.md)
POLLS = [(dt.date(2026, 10, 21), "Poll 1", 1), (dt.date(2026, 10, 25), "Poll 2", 7000),   # 7,000 since 20 Oct
         (dt.date(2026, 10, 29), "Poll 3", 7000)]
MULTIPLIERS = [(dt.date(2026, 10, 26), 2), (dt.date(2026, 11, 1), 4)]     # derived, not confirmed by organisers
LOG_TAIL_BYTES = 6_000_000                     # likes are logged one per line; this covers several hours
STALE_STATUS_S = 300
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


def conversations(actions):
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
        total = sum(est.values())
        if len(est) == 1:
            share = {k: e["points"] for k in est}
        elif total and e["points"] / total > 0:
            share = {k: v * e["points"] / total for k, v in est.items()}
        else:                                      # signs disagree: our weights, the rest on the largest kind
            share = dict(est)
            big = max(est, key=lambda k: abs(est[k]))
            share[big] += e["points"] - total
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
    return dict(rows=rows, total=sum(e["points"] for e in points if e["_t"] >= since))


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
AUTO_UNDO = "ssh swan-ec2 'cd ctn && .venv/bin/python scripts/facts_review.py --undo {id}'"   # = factdesk.UNDO
AUTO_WORDS = {"accepted": "applied", "retired": "retired the fact", "logged": "idea logged",
              "failed": "left for a human", "undone": "undone"}


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
    log, ideas = [], []
    for r in reversed(autolog):
        t = ts(r.get("decided_at"))
        if not t:
            continue
        if r.get("status") == "logged":           # ideas change nothing: one line each, collapsed
            if len(ideas) < AUTO_SHOWN:
                ideas.append(dict(id=r.get("id"), time=perth(t).strftime("%a %H:%M"),
                                  text=short(props.get(r.get("id"), {}).get("idea") or r.get("summary"), 200)))
            continue
        if len(log) >= AUTO_SHOWN:
            continue
        p = props.get(r.get("id"), {})
        log.append(dict(
            id=r.get("id"), time=perth(t).strftime("%a %H:%M"), status=r.get("status"),
            word=AUTO_WORDS.get(r.get("status"), r.get("status")), label=KINDS.get(r.get("kind"), r.get("kind")),
            summary=short(r.get("summary"), 300), quote=short(r.get("quote") or p.get("quote"), 300),
            text=r.get("text") if r.get("status") == "accepted" else None, by=r.get("by"),
            url=f"https://sites.legitreal.com/{r.get('site')}/articles/{r.get('slug')}" if r.get("site") else None,
            undo=AUTO_UNDO.format(id=r.get("id")) if r.get("status") in ("accepted", "retired")
            and r.get("id") not in undone else None))
    auto = dict(on=bot_config.FACTDESK_AUTO, cap=bot_config.FACTDESK_AUTO_PER_DAY, log=log, ideas=ideas,
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
                             proposal=v.get("proposal")) for k, v in held.items()],
                proposals=items, count=len(items), auto=auto,
                reject_ideas=f"{REVIEW} --reject {','.join(map(str, rest))}" if len(rest) > 1 else None)


# ---- Blue (todo/07, src/swan_blue): only what the team needs to decide ----
BLUE_STALE_S = 10 * 60                         # swan-blue writes its status every minute
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


# Reports since 9pm, grouped by outcome (todo/29): genuine first and open (each one locks reporting), then the account
# reports with their outcome from the portal log, then hidden and refused, collapsed.
BLUE_GROUPS = (("genuine", "Ruled genuine", "down"), ("account", "Account reports ruled", ""),
               ("hidden", "Hidden (inauthentic)", "up"), ("refused", "Refused", "down"))
BLUE_ACCOUNT_PTS = 15                          # an upheld account report (scoring cheatsheet), times the line's ×rate
BATCH_S = 120                                  # portal lines this close together are one hourly scoring run
UPHELD = re.compile(r"(\d+) upheld account reports?", re.I)
RATE = re.compile(r"×\s*([\d.]+) points")


def account_outcomes(ledger, points):
    """{report key: (words, css)} for our ruled account reports. The API doesn't show them (a suspended account still
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
                out[r.get("key")] = ("ruled · outcome not in the portal log yet", "")
            else:
                batches.setdefault(id(run), (run, []))[1].append(r.get("key"))
    for run, keys in batches.values():
        k, n = min(run[1], len(keys)), len(keys)
        word = (f"suspended · +{run[2]:g}" if k == n else "dismissed (no points, no lock)" if k == 0 else
                f"suspended or dismissed: {k} of these {n} suspended")
        for key in keys:
            out[key] = (word, "up" if k == n else "" if k == 0 else "warn")
    return out


def blue_ledger(ledger, points):
    """(pending, groups). pending: the reports waiting for a ruling, by group of accounts (swan-blue's cluster
    label), with the earliest ruling time. groups: the rest by outcome, BLUE_GROUPS order, empty ones left out."""
    outcomes = account_outcomes(ledger, points)
    pend, groups = {}, {k: [] for k, _, _ in BLUE_GROUPS}
    for r in ledger:
        t = ts(r.get("at"))
        what = f"#{r['target']}" if r.get("kind") == "post" else f"account {r['target']}"
        row = dict(what=what, group=f"group {r.get('team') or '?'}", at=hm(t) if t else "", t=t, word="", css="")
        status = r.get("status")
        if status == "pending":
            pend.setdefault(row["group"], []).append(row)
        elif r.get("kind") != "post" and status == "ruled":
            row["word"], row["css"] = outcomes.get(r.get("key"), ("ruled", ""))
            groups["account"].append(row)
        elif status in groups:
            groups[status].append(row)
        else:                                  # a status we don't group: shown with the account outcomes' neighbours
            row["word"] = str(status)
            groups["refused" if status == "refused" else "account"].append(row)
    rows = [r for g in pend.values() for r in g]
    times = [r["t"] for r in rows if r["t"]]
    pending = dict(n=len(rows), oldest=hm(min(times)) if times else None,
                   accounts=sum(r["what"].startswith("account") for r in rows),
                   groups=sorted(([g, sorted(v, key=lambda r: r["at"])] for g, v in pend.items()),
                                 key=lambda gv: (-len(gv[1]), gv[0])))
    out = [dict(key=k, name=name, css=css, rows=sorted(groups[k], key=lambda r: r["at"], reverse=True))
           for k, name, css in BLUE_GROUPS if groups[k]]
    return pending, out


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
    portal = {}
    for e in points:
        msg = e.get("message") or ""
        if not BLUE_MSG.search(f"{e.get('type')} {msg}"):
            continue
        p = portal.setdefault(e["_t"].astimezone(SYDNEY).date().isoformat(),
                              dict(points=0, first=0, later=0, full=0, reduced=0))
        f, later = first_later([msg])
        full, reduced = awards_by_rate([msg])
        p["points"], p["first"], p["later"] = p["points"] + e["points"], p["first"] + f, p["later"] + later
        p["full"], p["reduced"] = p["full"] + full, p["reduced"] + reduced
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
    pts = sum(e["points"] for e in points if e["_t"] >= day_start and re.search(
        r"moderat|inauthentic|suspen|report", f"{e.get('type')} {e.get('message')}", re.I))
    rings = [dict(post=r.get("post"), why=short(r.get("why"), 160), reports=r.get("reports"))
             for r in s.get("rings") or []]
    waiting = len(s.get("waiting") or [])
    pending, groups = blue_ledger(s.get("ledger") or [], points)
    own = own_reported(s.get("own_ids"), logs or data.parent / "logs")
    history = blue_days(s.get("days") or {}, points, now)
    last = next((r for r in history if not r["today"]), None)       # the last finished day decides the verdict
    ready = s.get("ready_ok", s.get("ready")) or 0
    lock_why = short(s.get("lock_why") or "reason not recorded", 60)
    bits = ([f"OUR OWN ACCOUNTS REPORTED: {own['hits']}"] if own and own["hits"] else []) + \
        ([f"last day {last['pct']}% of target"] if last else []) + \
        ([f"{waiting} waiting for approval"] if waiting else []) + \
        ([f"locked until {hm(locked)} Perth ({lock_why})", f"{ready} ready"] if locked else []) + \
        ([f"{s['pending']}/{s['cap']} pending"] if s.get("pending") else []) + \
        ([f"{today.get('hidden', 0)} hidden since 9pm"] if today.get("filed") else []) + \
        ([f"{pts:+,} pts since 9pm"] if pts else [])
    return dict(
        stale=t is None or (now - t).total_seconds() > BLUE_STALE_S, ago=ago(now - t) if t else "never",
        summary=" · ".join(bits) or "nothing to report right now", why=s.get("why"),
        locked=hm(locked) if locked else None, lock_why=s.get("lock_why"), pending=s.get("pending"),
        lock_estimate=s.get("lock_src") == "estimate", ready=ready, ready_accounts=s.get("ready_accounts") or 0,
        pg_max=s.get("pg_max"), pg_check={"n": 0, **(s.get("pg_check") or {})},
        clusters={"today": 0, "full": 0, **(s.get("clusters") or {})},
        next_ruling=hm(nxt) if nxt else None, waiting=waiting, rings=rings,
        teams=len({r.get("team") for r in s.get("rings") or []}),
        ev=round(sum(r.get("ev") or 0 for r in s.get("rings") or [])), approve=BLUE_APPROVE,
        today={k: today.get(k) or 0 for k in ("filed", "hidden", "genuine", "refused", "accounts")},
        queued=s.get("queued") or 0, first={"first": 0, "later": 0, **(s.get("first") or {})}, queue=pending, groups=groups, own=own,
        rows=[r for _, rows in pending["groups"] for r in rows] + [r for g in groups for r in g["rows"]],
        # todo/28's fields: the genuine-risk bucket, risk per evidence class, co-reported rulings, account detectors
        risk=s.get("risk") and {"level": 0, "cap": 0, "per_day": 0, "posts_now": 0, **s["risk"]},
        co=s.get("co") if (s.get("co") or {}).get("of") else None,
        pg_by_class=sorted(((plain(k), {"n": 0, "genuine": 0, "expected": 0, **v})
                            for k, v in (s.get("pg_by_class") or {}).items()), key=lambda kv: -kv[1]["n"]),
        detect=s.get("detect") and {"posts_seen": 0, "groups": 0, "by": {}, **s["detect"]},
        rate=prec.get("rate"), ruled=prec.get("n"), history=history, last=last, target=BLUE_TARGET_DAY,
        error=s.get("last_error") if err_t and (now - err_t).total_seconds() < BLUE_ERROR_S else None)


# ---- reach: did we answer every citizen we could, fast, and did it convert? (Marc, 2026-10-22) ----
CITIZEN_WRITES = {"reply", "reply_back", "second_voice", "journalist"}
REACH_SPEED_MIN = 3            # a new citizen post answered within this (median)
REACH_BACK_MIN = 1             # a citizen answering us gets our reply within this (median)
REACH_PACE_SHARE = 0.9         # writes a minute under this share of the bot's pace, citizens waiting: amber
REACH_SHARE = 0.9              # answered / answerable, and drafts passing on the first LLM call
REACH_CONVERT_AFTER = 100      # citizen-facing writes today before "no change toward No" counts as a problem
MIND = re.compile(r"(\d+) (.*)")


def _id_clock(actions):
    """(post id, unix time) of our own live writes: ids rise with time, so a citizen post's id dates it."""
    pts = []
    for a in actions:
        try:
            if a.get("live") is True and a.get("act") in WRITES and a.get("post_id") not in (None, "None"):
                pts.append((int(a["post_id"]), a["_t"].timestamp()))
        except (TypeError, ValueError):
            pass
    return sorted(pts)


def _written_at(pid, clock):
    """When post `pid` was written, interpolated between our own posts; None outside what we can date."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    for (i0, t0), (i1, t1) in zip(clock, clock[1:]):
        if i0 <= pid <= i1 and i1 > i0:
            return t0 + (t1 - t0) * (pid - i0) / (i1 - i0)
    return None


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
    """The Reach block: one summary line, then one short row per check (light, now, target) and a fix only for rows
    that aren't green. Collapsed while everything is green (Marc, 2026-10-22: scannable, not sentences)."""
    hour_ago = now - dt.timedelta(hours=1)
    refreshes = [a for a in actions if a.get("act") == "refresh"]
    funnel = (refreshes[-1].get("funnel") if refreshes else None) or {}
    keys = sorted(funnel)
    f = funnel[keys[-2]] if len(keys) >= 2 else (funnel[keys[-1]] if keys else None)    # the last full hour
    rows = []

    def row(name, light, now_, target, fix=""):
        rows.append(dict(name=name, light=light, now=now_, target=target, fix=fix))

    # answered (last full hour)
    tile = None
    if f:
        skipped, lost, pending = (f.get(k) or {} for k in ("skipped", "lost", "pending"))
        n_lost, n_wait = sum(lost.values()), sum(pending.values())
        answerable = max(f.get("seen", 0) - sum(skipped.values()), 0)
        light = "red" if n_lost else ("amber" if answerable and f.get("answered", 0) / answerable < REACH_SHARE
                                      and not n_wait else "green")
        share = f.get("answered", 0) / answerable if answerable else 1.0
        row("Citizens answered (last full hour)", light,
            f"{f.get('answered', 0)} of {answerable} ({share:.0%})" + (f" · {n_wait} waiting" if n_wait else "")
            + (f" · {n_lost} lost" if n_lost else " · 0 lost"), "all · 0 lost",
            "Citizens lost: " + ", ".join(f"{v} {k}" for k, v in lost.items()) + ". Tell targeting / drafting." if n_lost
            else "Some answerable citizens weren't answered: check Activity.")
        tile = dict(answered=f.get("answered", 0), answerable=answerable, share=share, lost=n_lost, light=light)
    else:
        skipped = {}
        row("Citizens answered", "amber", "no figures yet", "all · 0 lost", "The bot isn't refreshing: check Bot.")

    # reply times
    clock = _id_clock(actions)
    fresh, back = [], []
    for a in actions:
        if a.get("live") is not True or a["_t"] < hour_ago or a.get("group") not in (None, "None"):
            continue
        w = _written_at(a.get("target_post"), clock)
        lag = (a["_t"].timestamp() - w) / 60 if w is not None else None
        if lag is None or lag < 0:
            continue
        if a.get("act") == "reply" and a.get("source") == "latest":
            fresh.append(lag)
        elif a.get("act") == "reply_back":
            back.append(lag)
    mf, mb = _median(fresh), _median(back)
    row("Reply time, new citizen posts", "amber" if mf and mf > REACH_SPEED_MIN else "green",
        f"{mf:.1f} min" if mf is not None else "none this hour", f"≤ {REACH_SPEED_MIN} min",
        "Behind the citizen's session: check the LLM line under Bot.")
    row("Reply time, citizens answering us", "amber" if mb and mb > REACH_BACK_MIN else "green",
        f"{mb:.1f} min" if mb is not None else "none this hour", f"≤ {REACH_BACK_MIN} min",
        "Reply-backs are slow: check Bot.")
    if tile:
        tile["speed"] = mf

    # throughput: writes a minute in the last full hour against the team budget and the bot's pace (Marc, 22 Oct:
    # "longest wait" swung with the time of day and said little). Amber only when the budget idled while citizens waited.
    hour_end = now.replace(minute=0, second=0, microsecond=0)
    full_hour = [a for a in actions if a.get("live") is True and a.get("act") in WRITES
                 and hour_end - dt.timedelta(hours=1) <= a["_t"] < hour_end]
    budget = (status.get("write_budget") or {}).get("limit") or TEAM_CAP_PER_MIN
    pace = status.get("per_min")
    rate = len(full_hour) / 60
    q = status.get("queue") or {}
    waiting = q.get("candidates", refreshes[-1].get("candidates") if refreshes else None)
    groups_q = sum((g or {}).get("queued") or 0 for g in ((refreshes[-1].get("groups") if refreshes else None) or {}).values())
    # citizens left waiting in that same hour (the funnel); without one, the queue now
    waited = sum((f.get("pending") or {}).values()) if f else (waiting or 0)
    behind = pace is not None and rate < pace * REACH_PACE_SHARE and waited > 0
    row("Throughput (last full hour)", "amber" if behind else "green",
        f"{rate:.1f}/min of {budget:.1f} ({rate / budget:.0%})" + (f" · pace {pace:g}" if pace is not None else ""),
        f"≥ pace{f' {pace:g}' if pace is not None else ''}/min",
        "The budget idled while citizens waited: the drafter is slower than the writer. Check the LLM line under Bot.")

    # writes (budget)
    hour_writes = [a for a in actions if a.get("live") is True and a.get("act") in WRITES and a["_t"] >= hour_ago]
    grp = [a for a in hour_writes if a.get("group") not in (None, "None")]
    cit = [a for a in hour_writes if a.get("act") in CITIZEN_WRITES and a.get("group") in (None, "None")]
    cap = TEAM_CAP_PER_MIN * 60
    spare = max(cap - len(hour_writes), 0)
    by_group = {}
    for a in grp:
        by_group[a["group"]] = by_group.get(a["group"], 0) + 1
    row("Writes, last hour", "green",
        f"{len(cit)} citizens · {len(grp)} groups · {len(hour_writes) - len(cit) - len(grp)} other · {spare} spare",
        f"of {cap}", "")

    # rejections
    acc = [a for a in hour_writes if a.get("act") in CITIZEN_WRITES and a.get("llm_calls") not in (None, "None")]
    first = sum(str(a.get("llm_calls")) == "1" for a in acc)
    gate_lost = sum(1 for a in actions if a.get("act") == "lost" and str(a.get("why", "")).startswith("gate:")
                    and a.get("mode") in CITIZEN_WRITES and a["_t"] >= hour_ago)
    share1 = first / len(acc) if acc else None
    row("Drafts passing first time", "red" if gate_lost else ("amber" if share1 is not None and share1 < REACH_SHARE
                                                               else "green"),
        (f"{share1:.0%}" if share1 is not None else "—") + f" · {gate_lost} lost", f"≥ {REACH_SHARE:.0%} · 0 lost",
        "Citizens lost to rejections: tell the content session." if gate_lost
        else "No one lost; each rejection costs a repair. The content session tunes the prompts.")

    # outcome
    minds = _minds(points, day_start)
    cit_today = sum(1 for a in actions if a.get("live") is True and a.get("act") in CITIZEN_WRITES and a["_t"] >= day_start)
    worse, stuck = minds["toward"] < minds["away"], cit_today >= REACH_CONVERT_AFTER and minds["toward"] == 0
    row("Changes of mind today", "red" if worse else ("amber" if stuck else "green"),
        f"{minds['toward']} toward No · {minds['away']} away · {minds['neither']} neither ({cit_today} replies)",
        "toward > away", "Replies aren't moving people toward No: see the todo/20 read-out.")

    rows.insert(0, rows.pop())                    # changes of mind: the row that is about points, first
    bad = lambda names, levels=("red", "amber"): any(r["name"].startswith(names) and r["light"] in levels for r in rows)
    if bad(("Citizens answered", "Drafts passing"), ("red",)):
        verdict = "losing citizens"
    elif bad(("Citizens answered", "Reply time", "Throughput")):
        verdict = "falling behind"
    elif bad(("Changes of mind",)):
        verdict = "not converting yet"
    else:
        verdict = "keeping up"
    light = "red" if any(r["light"] == "red" for r in rows) else ("amber" if verdict != "keeping up" else "green")
    summary = " · ".join(x for x in (
        f"today {minds['toward']} toward No / {minds['away']} away / {minds['neither']} neither",
        tile and f"{tile['answered']}/{tile['answerable']} answered ({tile['share']:.0%})",
        tile and f"{tile['lost']} lost", mf is not None and f"reply {mf:.1f} min",
        f"{rate:.1f}/min of {budget:g}") if x)
    extra = []
    if skipped:
        extra.append("Skipped on purpose (last full hour): "
                     + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in sorted(skipped.items(), key=lambda kv: -kv[1])))
    if waiting is not None:
        extra.append(f"Queue now: {max(waiting - groups_q, 0)} citizens waiting"
                     + (f" · {groups_q} extra-group posts" if groups_q else ""))
    if by_group:
        extra.append("Extra groups (last hour): " + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in sorted(by_group.items())))
    for r in rows:
        r["note"] = next((v for k, v in (notes or {}).items() if r["name"].startswith(k)), "")
    return dict(verdict=verdict, light=light, summary=summary, rows=rows, tile=tile, extra=extra,
                open=light == "red", fixes=[r for r in rows if r["light"] != "green"])


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
    elif current:
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
    elif blue and blue["own"] and blue["own"]["hits"]:
        amber = (f"BLUE: {blue['own']['hits']} report(s) in logs/blue_reports.jsonl against our own accounts. "
                 f"Stop filing: ssh swan-ec2 'touch ctn/BLUE_OFF'")
    elif blue and blue["stale"]:
        amber = f"BLUE: no status from swan-blue since {blue['ago'].replace(' ago', '')}. On the box: journalctl -u swan-blue -n 50"
    elif blue and blue["waiting"]:
        amber = f"BLUE: {blue['waiting']} reports wait for your approval (Blue, below)"
    if red:
        banner = dict(level="red", text=red)
    elif amber:
        banner = dict(level="amber", text=amber)
    else:
        banner = dict(level="green", text="RUNNING · last post " + (ago(now - last_write) if last_write else "—"))

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
    history = [dict(time=perth(ts(x["ts"])).strftime("%a %H:%M"), score=x["score"], rank=x.get("rank"),
                    change=x["score"] - entries[i - 1]["score"] if i else None, by=x.get("by", "?"))
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
    rows = conversations(actions)
    for a in actions:
        act = a.get("act")
        if act == "register":
            rows.append(dict(t=a["_t"], who=a.get("persona") or a.get("role") or "", what="new account",
                             text=a.get("username"), kind="event"))
        elif act == "suspended":
            rows.append(dict(t=a["_t"], who="", what="SUSPENDED", text=a.get("username"), kind="bad"))
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
                rows.append(dict(t=ts(t), who="", what="post hidden", text=short(msg, 200), kind="bad"))
            else:
                rows.append(dict(t=ts(t), who="", what="alert", text=short(msg), kind="event"))
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

    deploys = [d for d in tail_jsonl(logs / "deploys.jsonl", 200_000) if d.get("result") == "ok"]
    running = dict(sha=deploys[-1]["new"][:7], when=hm(ts(deploys[-1]["ts"]))) if deploys else None

    return dict(
        now=hm(now), banner=banner, score=score, history=history, board=board, milestone=milestone,
        multiplier=multiplier, portal_accounts=portal.get("accounts"), score_lines=score_lines(points, day_start),
        portal_checked=ago(now - portal_t) if portal_t else None,
        day_start=perth(day_start).strftime("%-I%p").lower(),
        writes=dict(hour=writes_hour, planned=round(per_min * 60) if per_min else None, cap=TEAM_CAP_PER_MIN * 60),
        accounts=dict(live=acc.get("live"), live_cap=LIVE_CAP, used=acc.get("used"), total_cap=TOTAL_CAP,
                      suspended=acc.get("suspended"), voices=acc.get("voices"), boosters=acc.get("boosters")),
        llm=dict(model=chain[current]["model"] if current is not None else None,
                 rank=ordinal(current + 1) if current is not None else None, of=len(chain), parked=parked,
                 chain=states, busiest=busiest if busiest and busiest["calls"] else None),
        errors=dict(rate_limited=status.get("rate_limited_last_hour"), rejects=rejects_hour),
        activity=items[:ACTIVITY_TOP], older=items[ACTIVITY_TOP:ACTIVITY_ALL], running=running, pulse=pulse, facts=facts,
        blue=blue, reach=reach(actions, status, points, now, day_start, read_json(data / "reach_notes.json") or {}),
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
    try:                                       # the NPC lab's page (todo/25): its failure never stops the main page
        lab = dict(gather_lab(args.root), built=perth(now).strftime("%H:%M:%S"))
        write_atomic(args.out / "lab.html", render(lab, "lab.html.j2"))
    except Exception as e:                     # noqa: BLE001
        print(f"lab page: {type(e).__name__}: {e}")
    write_atomic(args.out / "robots.txt", "User-agent: *\nDisallow: /\n")
    write_atomic(args.out / "app.js", (pathlib.Path(__file__).parent / "templates" / "app.js").read_text())


if __name__ == "__main__":
    main()
