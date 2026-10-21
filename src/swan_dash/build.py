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

ROOT = pathlib.Path(__file__).resolve().parents[2]
PERTH = ZoneInfo("Australia/Perth")
SYDNEY = ZoneInfo("Australia/Sydney")          # competition days roll over at midnight Sydney (9pm Perth)
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


def fact_desk(root):
    """The Facts section: pauses that hold (facts.toml not re-checked since) and proposals without a committed
    decision (content/fact_decisions.jsonl), urgent first, each with its review command. None without the files."""
    try:
        table = {k: v for k, v in tomllib.loads((root / "content" / "facts.toml").read_text()).items()
                 if isinstance(v, dict)}
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return None
    pauses = read_json(root / "data" / "facts_paused.json") or {}
    held = {k: v for k, v in pauses.items() if isinstance(v, dict) and k in table
            and (_when(table[k].get("checked")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc))
            < (_when(v.get("since")) or dt.datetime.max.replace(tzinfo=dt.timezone.utc))}
    decided = {d.get("id") for d in tail_jsonl(root / "content" / "fact_decisions.jsonl")}
    props = {}
    for r in tail_jsonl(root / "data" / "fact_proposals.jsonl"):
        if "kind" in r and r.get("kind") in KINDS:
            props[r["id"]] = r
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
            hint=HINTS[p["kind"]], commands=commands))
    order = list(KINDS)
    items.sort(key=lambda i: (not i["paused"], order.index(i["kind"]), -i["id"]))
    rest = [i["id"] for i in items if i["kind"] == "angle"]
    return dict(paused=[dict(fact=k, since=hm(ts(v.get("since"))) if ts(v.get("since")) else "?",
                             proposal=v.get("proposal")) for k, v in held.items()],
                proposals=items, count=len(items),
                reject_ideas=f"{REVIEW} --reject {','.join(map(str, rest))}" if len(rest) > 1 else None)


# ---- Blue (todo/07, src/swan_blue): only what the team needs to decide ----
BLUE_STALE_S = 10 * 60                         # swan-blue writes its status every minute
BLUE_APPROVE = "ssh swan-ec2 'ctn/scripts/blue.sh approve all'"


def blue_panel(data, now, points, day_start):
    """The Blue section: mode, slots, lock, today's rulings, and the reports waiting for approval. None if not set up."""
    s = read_json(data / "blue_status.json")
    if not s:
        return None
    t = ts(s.get("ts"))
    locked = ts(s.get("locked_until"))
    nxt = ts(s.get("next_ruling"))
    prec = s.get("precision") or {}
    pts = sum(e["points"] for e in points if e["_t"] >= day_start and re.search(
        r"moderat|inauthentic|suspen|report", f"{e.get('type')} {e.get('message')}", re.I))
    return dict(
        stale=t is None or (now - t).total_seconds() > BLUE_STALE_S, ago=ago(now - t) if t else "never",
        mode=s.get("mode"), why=s.get("why"), pending=s.get("pending"), cap=s.get("cap"),
        locked=hm(locked) if locked else None, lock_why=s.get("lock_why"), next_ruling=hm(nxt) if nxt else None,
        today=s.get("today") or {}, rate=prec.get("rate"), ruled=prec.get("n"), points=pts,
        waiting=[dict(key=w["key"], age=w.get("age_min"), ev=w.get("ev"), why=short(w.get("why"), 200))
                 for w in s.get("waiting") or []],
        approve=BLUE_APPROVE, error=s.get("last_error"), reporter=s.get("reporter"))


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
    states = [dict(model=m["model"], state="in use" if i == current else
                   f"{m.get('why') or 'parked'} until {hm(dt.datetime.fromtimestamp(m['parked_until'], dt.timezone.utc))}"
                   if m.get("parked_until") else "ready", out=bool(m.get("parked_until")))
              for i, m in enumerate(chain)]
    acc = status.get("accounts") or {}
    banned_day = [a for a in actions if a.get("act") == "suspended" and a["_t"] >= now - dt.timedelta(hours=24)]
    per_min = status.get("per_min")

    facts = fact_desk(root)
    blue = blue_panel(data, now, points, day_start)

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
    elif banned_day:
        amber = f"ACCOUNT LOST: {len(banned_day)} suspended in the last 24 h ({banned_day[-1].get('username')})"
    elif status.get("rate_limited_last_hour"):
        amber = f"RATE-LIMITED: {status['rate_limited_last_hour']} × 429 in the last hour"
    elif portal.get("error"):
        amber = f"PORTAL: {portal['error']}"
    elif portal and (portal_t is None or (now - portal_t).total_seconds() > PORTAL_STALE_S):
        amber = "PORTAL: no score update for " + (ago(now - portal_t).replace(" ago", "") if portal_t else "a while")
    elif facts and facts["paused"]:
        amber = (f"FACT PAUSED: {', '.join(p['fact'] for p in facts['paused'])} (the bot leaves it out). "
                 f"Review it under Facts below")
    elif blue and blue["stale"]:
        amber = f"BLUE: no status from swan-blue since {blue['ago'].replace(' ago', '')}. On the box: journalctl -u swan-blue -n 50"
    elif blue and blue["waiting"]:
        amber = f"BLUE: {len(blue['waiting'])} reports wait for your approval (Blue, below)"
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

    # ---- activity: our writes, account events, long LLM parks, deploys and alerts ----
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
    for e in points:                           # the outcome, interleaved with what we did
        rows.append(dict(t=e["_t"], who="", what=f"{e['points']:+,} pts", text=short(e.get("message"), 160),
                         kind="gain" if e["points"] >= 0 else "loss"))
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
        multiplier=multiplier, portal_accounts=portal.get("accounts"),
        portal_checked=ago(now - portal_t) if portal_t else None,
        day_start=perth(day_start).strftime("%-I%p").lower(),
        writes=dict(hour=writes_hour, planned=round(per_min * 60) if per_min else None, cap=TEAM_CAP_PER_MIN * 60),
        accounts=dict(live=acc.get("live"), live_cap=LIVE_CAP, used=acc.get("used"), total_cap=TOTAL_CAP,
                      suspended=acc.get("suspended"), voices=acc.get("voices"), boosters=acc.get("boosters")),
        llm=dict(model=chain[current]["model"] if current is not None else None,
                 rank=ordinal(current + 1) if current is not None else None, of=len(chain), parked=parked,
                 chain=states),
        errors=dict(rate_limited=status.get("rate_limited_last_hour"), rejects=rejects_hour),
        activity=items[:ACTIVITY_TOP], older=items[ACTIVITY_TOP:ACTIVITY_ALL], running=running, pulse=pulse, facts=facts,
        blue=blue,
        built=perth(now).strftime("%H:%M:%S"))


def render(ctx):
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(pathlib.Path(__file__).parent / "templates"),
                             autoescape=True, undefined=jinja2.StrictUndefined, trim_blocks=True, lstrip_blocks=True)
    env.filters["n"] = lambda x: "—" if x is None else f"{x:,}"
    env.filters["short"], env.filters["hm"] = short, hm
    return env.get_template("index.html.j2").render(**ctx)


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
    write_atomic(args.out / "robots.txt", "User-agent: *\nDisallow: /\n")
    write_atomic(args.out / "app.js", (pathlib.Path(__file__).parent / "templates" / "app.js").read_text())


if __name__ == "__main__":
    main()
