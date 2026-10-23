"""todo/33 engagement per write: the free levers (a follow, a like) and the limits that keep them human.

The portal pays 5 points a like, 15 a reply, 20 a follow (x2 from 26 Oct, x4 on 1-2 Nov), uncapped, and almost nothing
for persuasion. A follow or a like has its own 30/min budget, so it costs no write. Which citizen gets which is
randomised per citizen, not per block: the effects land hours later and would smear across 2 h blocks.

  cell(citizen_id)        one of config.ENG_CELLS, a pure function of the id (sha256, the same on every machine);
  plan(...)               the actions a reply to that citizen queues: a follow seconds after it, a like minutes after;
  follow_block, like_block  why an action may not go now (None: go), from the persona's own record and the queue;
  budget_wait             seconds to wait for a route's budget, from the X-RateLimit-* the last answer reported.

Nothing here calls the platform; bot.engage_actions does, from the queue in state["eng_queue"], with writes off
unless the bot runs --live. Per persona record: rec["followed"] (account ids, all time) and rec["follow_times"]
(epoch seconds of the last day's follows, any reason).
"""
import hashlib
import random
import time

from . import config

DAY_S = 24 * 3600
FOLLOW_MODES = ("reply", "reply_back")      # a follow on our first reply; reply-back follows are the older behaviour
LIKE_MODES = ("reply", "reply_back")        # the post we reply to is the one liked
GAP_REASONS = ("gap", "pair", "budget")      # worth another try soon; the rest drop the action


def cell(citizen_id, cells=None):
    """The free-lever cell of a citizen: config.ENG_CELLS[sha256(id) % len]. Same id, same cell, on every machine
    and after every restart; the four cells come out within a few percent of equal over a few hundred ids."""
    cells = cells or config.ENG_CELLS
    n = int(hashlib.sha256(f"eng:{citizen_id}".encode()).hexdigest()[:12], 16)
    return cells[n % len(cells)]


def does(cell_name, lever):
    """Whether this cell does `lever` ("follow" or "like"), with the lever's config switch on."""
    on = config.ENG_FOLLOW if lever == "follow" else config.ENG_LIKE
    return bool(on) and lever in cell_name.split("+")


def note_follow(rec, citizen_id, now=None):
    """Record a follow on the persona: the all-time list and the last day's times (what the daily cap counts)."""
    now = time.time() if now is None else now
    followed = rec.setdefault("followed", [])
    if citizen_id not in followed:
        followed.append(citizen_id)
    times = [x for x in rec.get("follow_times", []) if now - x < DAY_S]
    rec["follow_times"] = times + [now]


def follows_today(rec, now=None):
    now = time.time() if now is None else now
    return sum(1 for x in rec.get("follow_times", []) if now - x < DAY_S)


def follow_block(rec, citizen_id, last, now=None):
    """Why this persona may not follow this citizen now, or None. last: {citizen: {"follow": t, "like": t}}, the
    team's last actions per citizen (state["eng_last"]). "already" and "day_cap" end the action; "gap" (one follow a
    minute per persona) and "pair" (a like for the same citizen within ENG_PAIR_GAP_S) are tried again."""
    now = time.time() if now is None else now
    if citizen_id in rec.get("followed", []):
        return "already"
    times = [x for x in rec.get("follow_times", []) if now - x < DAY_S]
    if len(times) >= config.ENG_FOLLOWS_PER_DAY:
        return "day_cap"
    if times and now - max(times) < config.ENG_FOLLOW_GAP_S:
        return "gap"
    if now - (last.get(str(citizen_id)) or {}).get("like", 0) < config.ENG_PAIR_GAP_S:
        return "pair"
    return None


def like_block(citizen_id, last, now=None):
    """Why a like for this citizen's post may not go now ("pair": we followed them within ENG_PAIR_GAP_S), or None."""
    now = time.time() if now is None else now
    if now - (last.get(str(citizen_id)) or {}).get("follow", 0) < config.ENG_PAIR_GAP_S:
        return "pair"
    return None


def budget_wait(rl, margin=None):
    """Seconds until the route's budget, as the last answer reported it (a ctn.RateLimit: limit, remaining, reset), has
    `margin` calls left again; 0 with no headers or room to spare. The budget refills steadily, one call per
    reset / (limit - remaining) seconds, as bot.header_gap reads it for the write route."""
    margin = config.ENG_BUDGET_MARGIN if margin is None else margin
    if rl is None or rl.limit <= 0:
        return 0.0
    short = (margin + 1) - rl.remaining
    if short <= 0:
        return 0.0
    return short * rl.reset / max(rl.limit - rl.remaining, 1)


def plan(job, rec, citizen_id, post_id, now=None, rng=random):
    """The queue entries a sent reply to `citizen_id` earns, given its cell: [] for none (and for a mode the levers
    don't touch). A reply-back follows the citizen in every cell (config.ENG_FOLLOW_ANSWERED, the bot's older behaviour,
    now through the same gates); the follow cells also follow on the first reply. job: the sent job (mode, draft_id). post_id: the citizen's post we answered (what a like is for).
    Each entry: kind, due, username (the persona), citizen, post_id, cell, mode, draft_id, tries."""
    now = time.time() if now is None else now
    name = cell(citizen_id)
    base = dict(username=rec["username"], citizen=citizen_id, post_id=post_id, cell=name, mode=job["mode"],
                draft_id=job.get("draft_id"), tries=0)
    answered = job["mode"] == "reply_back" and config.ENG_FOLLOW_ANSWERED
    out = []
    if (job["mode"] in FOLLOW_MODES and (does(name, "follow") or answered)
            and citizen_id not in rec.get("followed", [])):
        out.append(dict(base, kind="follow", why="answered" if job["mode"] == "reply_back" else "first_reply",
                        due=now + rng.uniform(*config.ENG_FOLLOW_DELAY_S)))
    if job["mode"] in LIKE_MODES and does(name, "like") and post_id:
        out.append(dict(base, kind="like", why=job["mode"], due=now + rng.uniform(*config.ENG_LIKE_DELAY_S)))
    return out


def push(state, entries):
    state.setdefault("eng_queue", []).extend(entries)


def first_contacts(rows):
    """{citizen: first reply row} among citizen-facing writes with an eng_cell, oldest first: the cohort the
    follow-back reads are for. Rows need act, eng_cell, target_author, post_id, account_id (the voice), ts."""
    out = {}
    for r in rows:
        if r.get("act") in FOLLOW_MODES and r.get("eng_cell") and r.get("target_author") and r.get("post_id"):
            out.setdefault(str(r["target_author"]), r)
    return out
