"""Operation Swan bot (Vote No). DRY-RUN BY DEFAULT: nothing is registered or posted without --live.

Every write slot goes to the most valuable job (docs/06-strategy/second-mover-plan.md):
  1. reply back to a citizen who replied to us
  2. second voice: a different persona and angle on a doubt we answered 10-30 min ago
  3. reply to an undecided citizen (mostly in the news threads), answering the doubt they voiced
  4. reply to a journalist's referendum post (at most one per 45 min)
  5. persona post, at most 1 in every 4 writes
If nothing is worth writing, it waits. Accounts are registered one at a time, 20-40 min apart.

With config.SPLIT_LOOP (todo/22) the same decisions run on three threads, so no write waits for a read or a draft: a
reader (targets and reply-backs), a drafter (chooses the next job in the order above and drafts it ahead) and the
writer (this main thread, the only one that writes to Legit Social). docs/04-technical/swan-bot-runbook.md.

With --amplify (todo/04-reach-amplification.md), persona posts are replaced by one amplified original every 10-16 min:
like-only booster accounts and the other voices like it on an organic-looking schedule, other voices reply in its
thread and repost it (those writes come first in the order above, after reply-backs). See amplify.py.
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import random
import re
import secrets
import signal
import subprocess
import threading
import time
import traceback

import openai
import capturethenarrative as ctn

from . import batch, config, content, experiment, feeds, humanize, pulse, quality, stealth, themes, watch
from .amplify import Amplifier
from .llm import Generator
from .targeting import YES_REASON, Targeter, classify, contact, messengers, sessions, soft_yes, stance, target_class

REPLY_BACK_JOBS = 10          # reply-back jobs read per poll (todo/20 G7; was 3)
REPLY_BACK_GAP_S = 60         # a reply-back waits this long after its voice's last write (not the 4-min gap)
WAIT_S = dict(no_voice=30, nothing=45, priority=15)   # a loop with nothing to do waits this long (s)
IDLE_S = 1.0                  # split loop: the writer looks for a ready draft this often (s)
JOIN_S = 10.0                 # split loop: on a stop, how long the writer waits for the other threads (s)


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat()


_LOG_LOCK = threading.Lock()  # the split loop's threads all log


def log(rec):
    config.LOGS.mkdir(exist_ok=True)
    line = json.dumps({"ts": now_iso(), **rec}) + "\n"
    with _LOG_LOCK, open(config.ACTIONS_LOG, "a") as f:
        f.write(line)


def load_json(path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, obj, private=False):
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1))
    if private:
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def pace_gap(per_min):
    """Seconds from one write to the next at per_min on average: 60 / per_min, times WRITE_JITTER (todo/24; the live
    pace was 0.7-1.5, 10% slow on average, from todo/03 to 22 Oct)."""
    return 60.0 / per_min * random.uniform(*config.WRITE_JITTER)


def header_gap(rl, margin=None):
    """Seconds until the team's write budget, as our last write's X-RateLimit-* reported it, has margin + 1 writes in
    it again, so our next write leaves `margin` for the swarm's reposts (todo/24). The bucket refills steadily: the
    writes it is short of come back over `reset` seconds, one every reset / (limit - remaining). 0 with no headers."""
    margin = config.WRITE_MARGIN if margin is None else margin
    if rl is None or rl.limit <= 0:
        return 0.0
    short = (margin + 1) - rl.remaining
    if short <= 0:
        return 0.0
    return short * rl.reset / max(rl.limit - rl.remaining, 1)


def write_gap(rl, per_min):
    """Seconds from this write to our next: never faster than pace_gap(per_min) on average, and never before the
    headers say the budget is back above the margin (header_gap). A 429 still waits its Retry-After (handle())."""
    return max(pace_gap(per_min), header_gap(rl))


def alert(msg):
    """deploy/alert.sh: a line in logs/alerts.log and the team webhook, like the BOT CRASHED alert. Never raises."""
    try:
        subprocess.run([str(config.ROOT / "deploy" / "alert.sh"), msg], timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        print("alert not sent:", e)


class Accounts:
    """Registry of our accounts in secrets/swan_accounts.json (passwords, tokens, owner)."""

    def __init__(self, social, live):
        self.social, self.live = social, live
        self.records = load_json(config.ACCOUNTS_FILE, []) if live else []
        self.open = {}
        self.next_register = 0.0
        self._hidden, self._hidden_mtime = {}, None
        self.reserved = set()        # personas with a draft not sent yet (split loop): not picked for another
        created = [dt.datetime.fromisoformat(r["created"]).timestamp() for r in self.records
                   if r.get("created") and r.get("role", "voice") != "booster"]
        if created:                      # a restart must not register straight after the last registration
            self.next_register = max(created) + random.uniform(*config.REGISTER_GAP_S)

    def save(self):
        if self.live:
            save_json(config.ACCOUNTS_FILE, self.records, private=True)

    def active(self):
        return [r for r in self.records if r.get("status", "active") == "active"]

    def usable(self):
        """Active accounts the bot may act as: all but swan_blue's reporter (it holds its own session)."""
        reporter = config.blue_reporter(self.records) if self.live else None
        return [r for r in self.active() if r is not reporter]

    def voices(self):
        """Persona accounts that write. Boosters (role 'booster') only view and like."""
        return [r for r in self.active() if r.get("role", "voice") != "booster"]

    def boosters(self):
        """Like-only accounts, less the one swan_blue reports from (config.blue_reporter)."""
        reporter = config.blue_reporter(self.records) if self.live else None
        return [r for r in self.active() if r.get("role") == "booster" and r is not reporter]

    def maybe_register(self, k, code, owner):
        """Drip registration: at most one new account per call, 20-40 min apart, never more than MAX_ACCOUNTS."""
        voices_ever = [r for r in self.records if r.get("role", "voice") != "booster"]
        if (len(self.voices()) >= k or len(voices_ever) >= config.MAX_ACCOUNTS
                or len(self.active()) + config.swarm_active() >= config.MAX_ACTIVE
                or time.time() < self.next_register):
            return
        used = {r["persona"] for r in self.records}
        spare = [p for p in content.PERSONAS if p["key"] not in used]
        if not spare:
            return
        p = spare[0]
        self.next_register = time.time() + random.uniform(*config.REGISTER_GAP_S)
        if not self.live:
            self.records.append(dict(persona=p["key"], username=f"(dry){p['handle']}", account_id=None,
                                     status="active", last_write=0, writes=0))
            return
        username = f"{p['handle']}{random.randint(10, 99)}"[:32]
        password = secrets.token_urlsafe(18)
        acc = self.social.register(username, password, code, display_name=p["name"])
        rec = dict(persona=p["key"], username=username, password=password, token=acc.token,
                   account_id=acc.account_id, owner=owner, created=now_iso(), status="active",
                   last_write=0, writes=0, followed=[])
        self.records.append(rec)
        self.open[username] = acc
        self.save()
        log({"act": "register", "username": username, "account_id": acc.account_id, "persona": p["key"], "owner": owner})
        print(f"registered {username} (id {acc.account_id}) for {owner}; next in "
              f"{(self.next_register - time.time()) / 60:.0f} min")

    def session(self, rec):
        acc = self.open.get(rec["username"])
        if acc is None:
            acc = self.social.account_from_token(rec["token"])
            self.open[rec["username"]] = acc
        return acc

    def relogin(self, rec):
        acc = self.social.login(rec["username"], rec["password"])
        rec["token"] = acc.token
        self.open[rec["username"]] = acc
        self.save()
        return acc

    def hidden(self):
        """{username: moderator-hidden posts} from scripts/swan_watch.py (data/swan_watch.json, re-read on change)."""
        try:
            mtime = watch.WATCH_FILE.stat().st_mtime
        except OSError:
            return {}
        if mtime != self._hidden_mtime:
            self._hidden_mtime = mtime
            self._hidden = {u: len(p) for u, p in watch.load().get("hidden", {}).items()}
        return self._hidden

    def parked(self, rec):
        """Too many hidden posts to write again (config.HIDDEN_STOP): a person decides what happens to it."""
        return self.hidden().get(rec["username"], 0) >= config.HIDDEN_STOP

    def rest(self, rec, t=None, citizen=True):
        """Why this voice keeps from writing now under todo/31's human day ("voice_asleep", "voice_capped"), or None.
        citizen: the write is to a citizen (the end of the daily budget is kept for those). Live only."""
        return stealth.rest(rec, t, citizen) if self.live else None

    def gap_ok(self, rec, t):
        """Its jittered gap, or the start stagger, has passed (todo/31; an ordinary write's gap, live only)."""
        return not (self.live and stealth.gap_on()) or rec.get("next_ok", 0) <= t

    def status(self, rec, t=None, citizen=True):
        """What holds this voice now, for status.json: parked, voice_asleep, voice_capped, gap, or None (free).
        citizen=False: for a write that isn't to a citizen (capped earlier, VOICE_CITIZEN_RESERVE)."""
        t = time.time() if t is None else t
        if self.parked(rec):
            return "parked"
        gap = config.ACCOUNT_MIN_GAP_S if self.live else 0
        return self.rest(rec, t, citizen) or (None if self.gap_ok(rec, t) and rec.get("last_write", 0) + gap <= t
                                              else "gap")

    def resting(self, t=None, citizen=True):
        """The reason most of the unparked voices keep from writing when none of them is free or merely in its gap,
        else None: the skip reason that explains a quiet writer (todo/31). citizen: as in status()."""
        t = time.time() if t is None else t
        states = [self.status(r, t, citizen) for r in self.voices() if not self.parked(r)]
        if not states or None in states or "gap" in states:
            return None
        why = [s for s in states if s in ("voice_asleep", "voice_capped")]
        return max(set(why), key=why.count) if why else None

    def ready(self, rec, t=None, citizen=True):
        """May this voice write now (its per-account gap has passed, and todo/31's human day allows it)?"""
        t = t or time.time()
        gap = config.ACCOUNT_MIN_GAP_S if self.live else 0
        return (rec.get("status", "active") == "active" and not self.parked(rec)
                and rec.get("last_write", 0) + gap <= t and self.gap_ok(rec, t) and not self.rest(rec, t, citizen))

    def assignable(self, frame=None, exclude=(), prefer=(), citizen=False):
        """Like eligible(), but the voice may still be in its gap: for batched drafts that wait in the pool."""
        t = time.time()
        free = [r for r in self.voices() if r["persona"] not in exclude and r["persona"] not in self.reserved
                and not self.parked(r) and not self.rest(r, t, citizen)]
        mine = [r for r in free if r["persona"] in prefer]
        if mine:
            free = mine
        elif frame:
            free = [r for r in free if frame in content.PERSONA_BY_KEY[r["persona"]]["frames"]] or free
        return min(free, key=lambda r: r.get("last_write", 0)) if free else None

    def eligible(self, frame=None, exclude=(), gap=None, prefer=(), citizen=False):
        """The voice that wrote longest ago among those free now: a shared-identity messenger (prefer) first,
        then personas whose home frames include the frame. todo/31: not asleep or capped (citizen: the write is to a
        citizen, so the end of the daily budget is open to it), and an ordinary write (gap None) waits for the
        voice's jittered gap; a repost (gap given) only for its own."""
        t = time.time()
        jitter = gap is None
        if gap is None or not self.live:                         # dry runs rotate personas without waiting
            gap = config.ACCOUNT_MIN_GAP_S if self.live else 0
        ready = [r for r in self.voices() if r.get("last_write", 0) + gap <= t and r["persona"] not in exclude
                 and r["persona"] not in self.reserved and not self.parked(r)
                 and (not jitter or self.gap_ok(r, t)) and not self.rest(r, t, citizen)]
        mine = [r for r in ready if r["persona"] in prefer]
        if mine:
            ready = mine
        elif frame:
            fit = [r for r in ready if frame in content.PERSONA_BY_KEY[r["persona"]]["frames"]]
            ready = fit or ready
        return min(ready, key=lambda r: r.get("last_write", 0)) if ready else None

    def by_persona(self, key):
        return next((r for r in self.voices() if r["persona"] == key), None)


class Sessions:
    """The reader thread's own sessions (todo/22): a client keeps the X-RateLimit-* of its last answer, so the reader
    must not share the writer's. A token the writer renewed (Accounts.relogin) is picked up on the next poll."""

    def __init__(self, social):
        self.social, self.open = social, {}

    def get(self, rec):
        acc, token = self.open.get(rec["username"], (None, None))
        if acc is None or token != rec["token"]:
            acc, token = self.social.account_from_token(rec["token"]), rec["token"]
            self.open[rec["username"]] = (acc, token)
        return acc


class Worker(threading.Thread):
    """One of the split loop's threads: runs step() until stop is set, noting each round in beats (todo/22). An
    exception ends it and is kept for the writer's watchdog, which stops the bot (problem())."""

    def __init__(self, name, step, stop, beats, silent_s):
        super().__init__(name=name, daemon=True)
        self.step, self.stop, self.beats, self.silent_s = step, stop, beats, silent_s
        self.error = None

    def run(self):
        try:
            while not self.stop.is_set():
                self.beats[self.name] = time.time()
                self.step()
        except BaseException as e:               # noqa: B036 - kept for the watchdog, which exits the process
            self.error = e
            traceback.print_exc()

    def problem(self, now=None):
        """Why this thread can't be relied on (it died, stopped, or went silent for silent_s), or None."""
        now = time.time() if now is None else now
        if self.error is not None:
            return f"{type(self.error).__name__}: {self.error}"[:300]
        if not self.is_alive():
            return "stopped"
        silent = now - self.beats.get(self.name, now)
        return f"no heartbeat for {silent:.0f} s" if silent > self.silent_s else None


def voice_wait(job, accounts, live, t=None):
    """Seconds until this job's voice may write: its last write plus the gap the choosing code used (a reply-back 60 s,
    a repost or an own-thread answer REPOST_MIN_GAP_S, everything else the 4-min ACCOUNT_MIN_GAP_S). 0 in a dry run.
    The split loop's writer checks it at send time, since a draft may have waited (todo/22)."""
    if not live:
        return 0.0
    mode, t = job["mode"], time.time() if t is None else t
    gap = (REPLY_BACK_GAP_S if mode == "reply_back" else config.REPOST_MIN_GAP_S if mode in ("repost", "thread_answer")
           else config.ACCOUNT_MIN_GAP_S)
    wait = job["rec"].get("last_write", 0) + gap - t
    if gap == config.ACCOUNT_MIN_GAP_S and stealth.gap_on():          # todo/31: an ordinary write's jittered gap
        wait = max(wait, job["rec"].get("next_ok", 0) - t)
    return max(0.0, wait)


def gone_at_send(job, state, t=None):
    """Why a draft that waited may no longer go out (split loop, todo/22), or None: its target was answered meanwhile
    ("replied"), another voice of ours has the citizen today ("voice_owner", todo/31), or the citizen is now talking
    with SESSION_VOICES of our voices ("session_cap"). The serial loop checks the same when it chooses."""
    mode, target = job["mode"], job.get("target") or {}
    if mode in ("reply", "reply_back") and target.get("post_id") in state["replied_posts"]:
        return "replied"
    if stealth.owner_problem(state, job, t):        # todo/31: one voice per citizen per day
        return "voice_owner"
    if mode in ("reply", "second_voice"):
        voices = set(sessions(state["contacted"], t).get(str(target.get("author_id")), ())) | {job["rec"]["persona"]}
        if len(voices) > config.SESSION_VOICES:
            return "session_cap"
    return None


def citizen_texts(sent, ready=()):
    """Our latest citizen-facing texts, oldest first (todo/27 phrase budgets, quality.over_budget): what we sent to a
    citizen (state["recent_sent"]) and the drafts to citizens waiting for the writer, the last PHRASE_WINDOW."""
    out = [text for a, _, text in sent if config.is_citizen(a)]
    out += [d["text"] for d in ready if d.get("text") and config.is_citizen((d["job"].get("target") or {}).get("author_id"))]
    return out[-quality.PHRASE_WINDOW:]


def thread_root(post):
    return post.get("root_post_id") or post.get("post_id")


def same_target_texts(sent, ready, target):
    """Our texts to this citizen or in this thread: sent (state["recent_sent"], [author, thread root, text]) and the
    drafts waiting for the writer. The gate holds a draft to the strict near-duplicate threshold against these and
    to the loose one against the rest (todo/24, quality.near_duplicate)."""
    author, root = target.get("author_id"), thread_root(target)
    out = [text for a, r, text in sent if a == author or r == root]
    for d in ready:
        t = d["job"].get("target") or {}
        if d.get("text") and t and (t.get("author_id") == author or thread_root(t) == root):
            out.append(d["text"])
    return out


SESSION_MODES = ("reply", "reply_back", "second_voice")     # the writes send() counts in state["contacted"]


def contacted_now(contacted, pending=(), t=None):
    """Our voices per citizen this session (targeting.sessions), counting the drafts chosen and not sent yet as sent
    (todo/24): the drafter then never drafts for a citizen those drafts will bring to SESSION_VOICES, a draft that
    gone_at_send would throw away (98 a night before). pending: held() jobs."""
    out = sessions(contacted, t)
    for j in pending:
        if j["mode"] in SESSION_MODES and j.get("target"):
            out.setdefault(str(j["target"]["author_id"]), set()).add(j["rec"]["persona"])
    return out


def thread_depth(social, post, cap):
    """How many posts sit above `post` in its thread, counted up to `cap` (one read per level, stopping there)."""
    depth, parent = 0, post.get("reply_to_post_id")
    while parent and depth < cap:
        depth += 1
        parent = social.get_post(parent).get("reply_to_post_id")
    return depth


def turns_left(turns, citizen, now=None):
    """Our reply-backs to this citizen may continue: fewer than TURNS_PER_SESSION in the last TURN_SESSION_S."""
    now = time.time() if now is None else now
    return sum(now - t < config.TURN_SESSION_S for t in (turns or {}).get(str(citizen), [])) < config.TURNS_PER_SESSION


def reply_back_jobs(social, accounts, targeter, limit=REPLY_BACK_JOBS, roots=None, turns=None, replied=(),
                    session=None):
    """Citizens who replied to us or mentioned one of our voices (todo/20 G7). Reads at most `limit` jobs' worth.
    A notification is resolved once it has been dealt with: queued, or skipped for a reason (logged). A read that
    fails for a moment (5xx, rate limit) leaves it unresolved for the next poll; 403/404/410 resolve it.
    roots: only replies under these posts of ours (our amplified posts), the rest are resolved and skipped.
    turns: {citizen id: [times of our reply-backs]} for the session cap; replied: posts we already answered.
    session: rec -> logged-in Account (default accounts.session; the split loop's reader has its own, Sessions)."""
    jobs = []
    for rec in accounts.voices():
        if len(jobs) >= limit:
            break
        try:
            acc = (session or accounts.session)(rec)
            notes = acc.notifications(unresolved=True, limit=10)
        except ctn.APIError as e:
            print("notifications:", rec["username"], e.status, e.message)
            continue
        for n in notes:
            if len(jobs) >= limit:
                break
            if n.get("kind") not in ("reply", "mention"):
                continue
            try:
                theirs = social.get_post(n["post"]["post_id"])
                skip = None
                if not config.is_citizen(theirs.get("author_id")):
                    skip = "not_citizen"
                elif theirs["post_id"] in replied:
                    skip = "replied"
                elif n["kind"] == "reply" and not theirs.get("reply_to_post_id"):
                    skip = "not_a_reply"
                elif roots is not None and theirs.get("reply_to_post_id") not in roots \
                        and theirs.get("root_post_id") not in roots:
                    skip = "not_our_thread"
                elif not turns_left(turns, theirs["author_id"]):
                    skip = "turn_cap"
                ours = None
                if not skip and theirs.get("reply_to_post_id"):
                    ours = social.get_post(theirs["reply_to_post_id"])
                    if thread_depth(social, ours, config.THREAD_MAX_DEPTH) + 1 >= config.THREAD_MAX_DEPTH:
                        skip = "deep_thread"
                if skip:
                    if skip not in ("not_citizen", "not_our_thread"):
                        log({"act": "skip", "why": skip, "mode": "reply_back", "target_post": theirs["post_id"],
                             "target_author": theirs.get("author_id"), "username": rec["username"]})
                else:
                    jobs.append(dict(mode="reply_back", rec=rec, target=theirs, tries=0, via=n["kind"],
                                     our_text=(ours or {}).get("body") or ""))
            except ctn.RateLimited:
                continue                                  # unresolved: the next poll tries again
            except ctn.APIError as e:
                if e.status not in (403, 404, 410):
                    print("reply-back read:", e.status, e.message)
                    continue
            try:
                acc.resolve_notification(n["notification_id"])
            except ctn.APIError as e:
                print("resolve:", rec["username"], e.status, e.message)
    return jobs


# the experiment arms (todo/13) logged on every write; the rest of meta is logged as before
ARMS = ("lever", "concede", "rebuttal", "ask_kind", "length_band", "reply_mode", "beat", "close", "theme_level",
        "block_id", "arm_conv", "fresh")
REJECT_ARMS = ("shape", "voice", "lever", "concede", "rebuttal", "ask_kind", "length_band", "reply_mode", "beat", "close",
               "pulse", "theme", "theme_level")


def experiment_fields(target, cls=None):
    """Run version and the target's stance class (H3), for the experiments report. Target text only: no reads.
    cls: the class targeting read with the thread as context (todo/21), when the job carries one."""
    body = (target or {}).get("body") or ""
    return {"exp": experiment.VERSION, "git_sha": experiment.git_sha(),
            **({"target_stance": stance(body), "target_class": cls or target_class(body), "soft_yes": soft_yes(body),
                "yes_reason": bool(YES_REASON.search(body))} if target else {})}


def second_frame(frame):
    second = content.FRAMES[frame]["second"]
    return content.live_frame(content.weighted_frame(second) if isinstance(second, list) else second)


def pick_post_shape(frame, persona, headline, recent_shapes):
    """An opening style that fits, used at most 2 times in the last 10 posts (todo/05 variety check)."""
    for _ in range(12):
        key, _text = content.pick_shape(frame, headline, persona=persona)
        if quality.shape_ok(key, recent_shapes):
            return key
    return None                                       # let post_prompt pick freely rather than stall


def pick_theme(job, ledger, meta):
    """job["theme"] for a post or a reply to a citizen (themes.py), or None; its choices land in meta."""
    target = job.get("target")
    job["theme"] = ledger.pick(job["rec"]["persona"], job["frame"], job["mode"],
                               thread=themes.thread_of(target) if target else None, meta=meta) if ledger else None
    return job["theme"]


def build_prompt(job, targeter, recent_shapes=(), pulse_now=None, ledger=None, recent_texts=()):
    """(persona, system, user). The choices made (shape, voice, tag, theme, event...) land in job["meta"].
    recent_texts: our latest drafts, so replies and second voices don't open the way they did (todo/20).
    pulse_now (todo/15): all of it for amplified posts (and a fresh hook as their news, about half the time), the
    hooks for thread replies, the Yes lines for replies to a Yes-leaner; nothing for the rest. With a ledger, posts
    and replies may carry a theme (themes.Ledger.pick)."""
    persona = persona_of(job["rec"])
    job.setdefault("frame_in", job.get("frame"))                 # the keyword match's frame, or None (todo/21)
    job["frame"] = content.live_frame(job["frame"], persona)      # a fact paused since the job was queued
    target = job.get("target") or {}
    body = target.get("body") or ""
    mode = job["mode"]
    meta = job["meta"] = {}
    parts = ()
    if mode in config.CONV_MODES:                                 # todo/25: the conversion arm of this 2 h block
        block_id, arm = experiment.block("arm_conv")
        meta.update(arm_conv=arm or "base", **({"block_id": block_id} if block_id else {}))
    if mode == "reply" and job.get("group") == "off_topic":      # todo/23: on their topic, no read, no theme
        job["style"], job["read"] = "off_topic", False
    elif mode == "reply":                # todo/20: the style arm in turn (the firm-Yes arm concedes first) and the read
        job["style"] = ("mirror_concede" if job.get("arm") == "firm_yes" else
                        experiment.alternate("style", config.REPLY_STYLES))
        job["read"] = config.LIGHT_READ
    mirror = job.get("style") in ("mirror_concede", "off_topic")  # four beats, or not about the vote: no theme
    theme = pick_theme(job, ledger, meta) if mode in themes.MODES and not mirror else job.setdefault("theme", None)
    if mode == "post":
        headline = targeter.headline if random.random() < 0.3 else None
        shape = None
        if job.get("amp") and pulse_now:
            parts = content.PULSE_PARTS
            hook = pulse.fresh_hook(pulse_now)
            if (hook and random.random() < config.PULSE_NEWS_SHARE
                    and quality.shape_ok("news", recent_shapes, max_uses=5)):
                headline, shape = hook, "news"
                meta["pulse_news"] = True
        user = content.post_prompt(job["frame"], headline,
                                   shape=shape or pick_post_shape(job["frame"], persona, headline, recent_shapes),
                                   ask=bool(job.get("amp")), meta=meta, persona=persona, theme=theme)
    elif mode == "thread":
        parts = ("hooks",) if pulse_now else ()
        user = content.thread_reply_prompt(body, job["frame"], job["style"])
    elif mode == "thread_answer":
        user = content.thread_answer_prompt(job["our_text"], body)
    elif mode == "reply" and job["style"] == "off_topic":
        user = content.off_topic_prompt(body, job.get("context"), persona)
        meta["style"] = "off_topic"
    elif mode == "reply":
        parts = ("yes_lines",) if pulse_now and (soft_yes(body) or YES_REASON.search(body)) else ()
        user = content.reply_prompt(body, job["frame"], job.get("wants"), job.get("context"), meta=meta, persona=persona,
                                    theme=theme, style=job["style"], read=job["read"], hint=job["frame_in"],
                                    recent=recent_texts)
        if meta.get("arm_conv") == "fresh_facts" and job["style"] != "off_topic":     # todo/25: news first
            fresh = content.fresh_line(body, meta)
            user = user.replace("\n\nFirst read them", f" {fresh}\n\nFirst read them", 1) \
                if job["read"] else f"{user} {fresh}"
        if content.group_style(job):                              # todo/23's groups: one line of guidance
            user = user.replace("\n\nFirst read them", f" {content.group_style(job)}\n\nFirst read them", 1) \
                if job["read"] else f"{user} {content.group_style(job)}"
    elif mode == "second_voice":
        user = content.second_voice_prompt(body, job["frame"], job.get("wants"), job.get("context"), meta=meta,
                                           persona=persona, recent=recent_texts)
    elif mode == "journalist":
        user = content.journalist_prompt(target["author_id"], body, meta=meta, persona=persona)
    else:
        user = content.reply_back_prompt(job["our_text"], body, style=job.get("style"))
        meta["style"] = job.get("style")
        if meta.get("arm_conv") == "fresh_facts":                 # todo/25: news first
            user = f"{user} {content.fresh_line(body, meta)}".rstrip()
    return persona, content.system_prompt(persona, job["frame"], meta=meta, pulse=pulse_now if parts else None,
                                          pulse_parts=parts), user


# Drafts at 0.7 keep to their shape and length better; own-thread reactions keep 0.9 for variety (todo/14)
TEMPERATURE = {"thread": 0.9, "thread_answer": 0.9}
# A 70-word post is ~100 tokens. Flash-lite spends no thinking tokens out of the cap (2026-10-21: max_tokens=120
# finished "stop" at 73), so this only stops a runaway answer
MAX_TOKENS = 600


def repair_prompt(user, raw, note):
    return (f"{user}\n\nYour draft was:\n<<<{raw}>>>\nFix only this: {note} Change as little as you can and keep "
            f"the rest. Output only the fixed text.")


THEME_REASONS = {"unplanned_slogan", "slogan_missing", "theme_without_reason", "theme_echo_repeat"}   # themes.draft_problem


def gate(raw, job, user, recent_texts, ledger=None):
    """(text, why, fixes): quality.check, the code fixes for what it rejects (quality.fix, at most 3, no LLM call),
    then the theme check. text is None when the draft still fails; fixes names the fixes that were applied."""
    mode, meta = job["mode"], job.get("meta") or {}
    kw = dict(prompt_text=user, target_text=(job.get("target") or {}).get("body") or "",
              wants=job.get("wants") or (), closing_question=meta.get("closing_question", True),
              specific=job.get("group") != "off_topic", same=job.get("same_texts") or (),
              phrase_texts=job.get("phrase_texts"))
    draft, fixes = raw, []
    text, why = quality.check(draft, mode, recent_texts, **kw)
    while why and len(fixes) < 3:
        fixed = quality.fix(draft, why, mode)
        if not fixed or fixed == draft:
            break
        fixes.append(why.split("_")[0] if why.startswith(("length_", "unapproved_")) else why)
        draft = fixed
        text, why = quality.check(draft, mode, recent_texts, **kw)
    theme_why = text and themes.draft_problem(text, job.get("theme"), mode, ledger)
    if theme_why:
        return None, theme_why, fixes
    return text, why, fixes


def draft_models(job, gen):
    """(models, ordered) for a draft. Amplified posts: AMP_MODELS (chain order). Replies to citizens (STRONG_MODES,
    todo/24): REPLY_MODELS in that order, then the rest of the chain, never REPLY_NEVER (ordered). Thread one-liners:
    the free models. Anything else: None, the whole chain."""
    chain = [m for _, m in getattr(gen, "chain", ())]
    if job.get("amp"):                                          # our best content
        return config.AMP_MODELS, False
    if job["mode"] in config.STRONG_MODES:                      # where minds change
        order = list(config.REPLY_MODELS) + [m for m in chain if m not in config.REPLY_MODELS]
        return [m for m in order if m not in config.REPLY_NEVER], True
    if job["mode"] in config.CHEAP_MODES:                       # one-liners: free models first, paid ones as backup
        return [m for m in chain if m not in config.LLM_PRICES], False
    return None, False


def complete_in_order(gen, system, prompt, models, **kw):
    """gen.complete on each model in turn (the chain's own order would put flash-lite before Kimi): the first answer,
    or (None, None). A parked or over-budget model returns at once, so this costs no extra time."""
    for m in models:
        raw, backend = gen.complete(system, prompt, models=(m,), **kw)
        if raw is not None:
            return raw, backend
    return None, None


def conv_models(gen, models):
    """todo/25's old_models arm: the 20 Oct free chain (config.CONV_OLD_MODELS) that isn't parked right now, then
    the usual reply order as the fallback."""
    parked = getattr(gen, "parked", {})
    old = [m for m in config.CONV_OLD_MODELS if time.time() >= parked.get(m, 0)]
    return old + [m for m in models or () if m not in config.CONV_OLD_MODELS]


def draft_checked(gen, job, system, user, recent_texts, on_reject=None, ledger=None):
    """Draft and gate (todo/20 G9: a citizen may not be lost to the gate). Each draft goes through gate(): the quality
    check and the code fixes, then the theme check. A draft that still fails goes back to the model with the exact
    problem (quality / themes repair_note; a fresh draft when there is no note), up to config.GATE_TRIES calls for
    the mode (2 otherwise). A model that failed twice is left out of the calls after that. Returns (text, backend,
    repair): text is None when every call failed, backend None when no model answered, repair the reject reason the
    last draft was repaired from. on_reject(why, raw, backend, repair) is called for each reject. job["meta"] gets
    llm_calls, repairs and fixes."""
    mode = job["mode"]
    meta = job.setdefault("meta", {})
    prompt, repair, backend = user, None, None
    models, ordered = draft_models(job, gen)
    if meta.get("arm_conv") == "old_models" and mode in config.STRONG_MODES:
        models = conv_models(gen, models)                       # todo/25: the usual order after the old chain
    failed = {}                                                 # model -> rejected drafts this job
    meta.update(llm_calls=0, repairs=0, fixes=[])
    for _ in range(config.GATE_TRIES.get(mode, 2)):
        tired = {m for m, n in failed.items() if n >= 2}
        use = [m for m in (models or [m for _, m in getattr(gen, "chain", ())]) if m not in tired] if tired else models
        kw = dict(max_tokens=MAX_TOKENS, temperature=TEMPERATURE.get(mode, 0.7), priority=bool(job.get("amp")))
        if ordered:                                             # replies: the whole order is already the fallback
            raw, backend = complete_in_order(gen, system, prompt, use or models, **kw)
        else:
            raw, backend = gen.complete(system, prompt, models=use or models, **kw)
        if raw is None and use and not ordered:                 # out of quota: the usual chain
            raw, backend = gen.complete(system, prompt, **kw)
        if raw is None:
            break
        meta["llm_calls"] += 1
        draft = raw
        if job.get("read"):                     # the light read: JSON on a fresh draft; a repair may answer plainly
            r = content.parse_read(raw)
            if prompt is user and not meta.get("read_ok"):
                meta.update(read_ok=r["ok"], read_stance=r["stance"],
                            read_doubt=r["doubt"], read_frame=r["frame"], read_skip=r["skip"])
                if r["frame"]:
                    job["frame"] = r["frame"]
                if (mode == "reply" and meta.get("arm_conv") == "no_leaners"
                        and r["stance"] in config.CONV_SKIP_STANCES and not r["skip"]):
                    r["skip"] = f"arm_conv:{r['stance']}"         # todo/25: No-leaners are left alone this block
            if r["skip"] and prompt is user:
                job["read_skip"] = r["skip"]
                return None, backend, None
            draft = r["reply"] or ""
        text, why, fixes = gate(draft, job, user, recent_texts, ledger)
        if text:
            meta["fixes"] = fixes
            return text, backend, repair
        failed[backend] = failed.get(backend, 0) + 1
        meta["last_reject"] = why
        if on_reject:
            on_reject(why, raw, backend, repair)
        note = (themes.repair_note(why, job.get("theme")) if why in THEME_REASONS else
                quality.repair_note(why, raw, mode, meta.get("tag"), recent=recent_texts))
        if note and job.get("read"):
            note += " Output only the fixed reply text, not JSON."
        prompt, repair = (repair_prompt(user, draft, note), why) if note else (user, None)
        meta["repairs"] += bool(note)
    return None, backend, repair


REPLY_BACK_TRIES = 3          # a citizen who answered us is drafted for this many slots before they're lost (G8)


def lose(targeter, queue, job, why):
    """A job whose draft failed (G8/G12). A reply to a citizen goes back to the targeter (its requeue backs off and
    logs the expiry); a reply-back goes to the back of the queue, REPLY_BACK_TRIES times; everything else, and
    anything that can't be put back, is logged as lost with the reason."""
    mode, target = job["mode"], job.get("target") or {}
    if mode == "reply" and job.get("cand") and hasattr(targeter, "requeue"):
        targeter.requeue(job["cand"], why)
        log({"act": "requeue", "why": why, "mode": mode, "target_post": target.get("post_id"),
             "draft_id": job.get("draft_id"), "tries": job["cand"].get("tries")})
        return "requeued"
    if mode == "reply_back" and job.get("tries", 0) < REPLY_BACK_TRIES - 1:
        job["tries"] = job.get("tries", 0) + 1
        queue.append(job)
        log({"act": "requeue", "why": why, "mode": mode, "target_post": target.get("post_id"),
             "draft_id": job.get("draft_id"), "tries": job["tries"]})
        return "requeued"
    log({"act": "lost", "why": why, "mode": mode, "target_post": target.get("post_id"),
         "target_author": target.get("author_id"), "draft_id": job.get("draft_id")})
    if target and mode in ("reply", "reply_back") and hasattr(targeter, "lose"):
        targeter.lose(target, why, job.get("source"))             # ends the citizen item in todo/21's funnel
    return "lost"


def own_likes(state, accounts, live, now=None):
    """todo/20 step 8: like our replies to citizens that are due a like (state["own_likes"]), one booster each, view
    first. A rate limit puts the like back a minute (3 tries); any other error drops it. Every like is logged with
    the account, its role and owner."""
    now = time.time() if now is None else now
    due = [x for x in state.get("own_likes", []) if x["due"] <= now]
    for x in due:
        state["own_likes"].remove(x)
        likers = [r for r in accounts.boosters() if not accounts.parked(r)] or \
                 [r for r in accounts.voices() if r["username"] != x["author"] and not accounts.parked(r)
                  and not (live and stealth.asleep(r["persona"], now))]          # todo/31: not in its sleep
        if not likers or x["post_id"] is None:
            continue
        rec = random.choice(likers)
        entry = {"act": "like", "live": live, "post_id": x["post_id"], "username": rec["username"],
                 "account_id": rec.get("account_id"), "role": rec.get("role", "voice"), "owner": rec.get("owner"),
                 "own": True, "purpose": "reply_like", "draft_id": x.get("draft_id")}
        if live:
            try:
                acc = accounts.session(rec)
                acc.view(x["post_id"])
                acc.like(x["post_id"])
            except ctn.RateLimited:
                if x.get("tries", 0) < 2:
                    state["own_likes"].append(dict(x, due=now + 60, tries=x.get("tries", 0) + 1))
                continue
            except ctn.APIError as e:
                log({**entry, "act": "like_failed", "error": e.status})
                continue
        log(entry)


CAND_INTERNAL = ("post", "score", "tries", "not_before")   # the targeter's own bookkeeping, not copied to the job


def reply_job(cand, rec):
    """A reply job from a targeter candidate. Every field the candidate carries reaches the job (frame, wants, context,
    source, identity, target_class, priority, arm, engaged, and todo/23's group and prefer), so a new field needs no
    change here. cand rides along: the drafting path requeues it on failure (G8)."""
    return dict({k: v for k, v in cand.items() if k not in CAND_INTERNAL}, mode="reply", rec=rec, target=cand["post"],
                cand=cand)


_REST_LOGGED = {}             # todo/31: why -> [time last logged, times seen since]


def log_rest(why, **fields):
    """A skip for todo/31's human day ("voice_asleep", "voice_capped", "voice_owner"), logged at most every
    STEALTH_LOG_S per reason, with n: how often it happened since the last line (the writer waits meanwhile)."""
    t = time.time()
    last = _REST_LOGGED.setdefault(why, [0.0, 0])
    last[1] += 1
    if t - last[0] < config.STEALTH_LOG_S:
        return
    log({"act": "skip", "why": why, "n": last[1], **fields})
    last[:] = [t, 0]


_TITLES = {"Mr", "Mrs", "Ms", "Dr", "Aunty", "Uncle", "Nana", "Papa"}


def persona_of(rec):
    """The persona card a voice drafts as. A booster turned voice (scripts/convert_boosters.py) takes only the card's
    role, place, frames and argument, under its own display name: the suspended voice's people, signature lines,
    events, arc and any text naming its people are left out, and its style and typing hand (`hand`) come from another
    suspended card (rec["converted"]["style_of"]), so it doesn't read as the old account back (todo/31)."""
    card = content.PERSONA_BY_KEY[rec["persona"]]
    conv = rec.get("converted")
    if not conv:
        return card
    style = content.PERSONA_BY_KEY.get(conv.get("style_of")) or card
    names = {w for x in card.get("people") or [] for w in re.findall(r"\b[A-Z][\w'-]+", x.split(",")[0])} - _TITLES
    named = re.compile(r"\b(" + "|".join(map(re.escape, sorted(names))) + r")\b") if names else None
    clean = lambda t: t if t and not (named and named.search(t)) else None
    return dict(card, name=rec.get("display_name") or card["name"], voice=style["voice"],
                register=style.get("register", card.get("register")), hand=style["key"],
                people=[], lines=[], now=[], arc=None, details=[d for d in card["details"] if clean(d)],
                covid=clean(card.get("covid")), problem=clean(card.get("problem")))


def candidate_voice(pick, cand, **kw):
    """The voice for a candidate: the one the citizen engaged with (cand["prefer"], todo/23) when it is free, else a
    shared-identity messenger, else one whose home frames fit. pick: accounts.eligible or accounts.assignable. The
    write is to a citizen, so the end of a voice's daily budget is open to it (citizen=True, todo/31)."""
    kw.setdefault("citizen", True)
    want = cand.get("prefer")
    if want:
        rec = pick(cand["frame"], prefer=(want,), **kw)
        if rec and rec["persona"] == want:
            return rec
    return pick(cand["frame"], prefer=messengers(cand.get("identity")), **kw)


OWNER_TRIES = 5               # todo/31: candidates looked at in one slot when their voice is held


def citizen_reply(targeter, accounts, our_ids, replied_posts, contacted, engaged=(), state=None):
    """The best waiting citizen candidate with a voice free to answer it, as a reply job, or None. contacted: our
    voices per citizen this session (targeting.sessions); engaged: citizens who replied to us before. frame is None
    when no doubt regex matched (the drafting call picks one, todo/20).
    todo/31, one voice per citizen per day (state's voice_of / thread_voice): a citizen one of our voices wrote to
    today is answered by that voice only. While it is asleep, capped or in its gap the citizen waits for it (backed
    off until it is free, 1-30 min at a time) and the next candidate is tried."""
    t = time.time()
    for _ in range(OWNER_TRIES):
        cand = targeter.next_target(our_ids, set(replied_posts), contacted, engaged)
        if not cand:
            return None
        want, conflict = stealth.required_voice(state or {}, cand["post"], t)
        if conflict:                                   # two voices have them today (one was mentioned): no third
            targeter.skip(cand["post"], conflict, cand.get("source"))
            log_rest(conflict, mode="reply", target_post=cand["post"]["post_id"])
            continue
        owner = accounts.by_persona(want) if want else None
        if owner is not None and not accounts.parked(owner):
            rec = accounts.eligible(cand["frame"], prefer=(want,), citizen=True)
            if rec and rec["persona"] == want:
                return reply_job(cand, rec)
            why = accounts.rest(owner, t) or "voice_owner"
            cand["not_before"] = t + min(max(stealth.free_in(owner, t), 60), 1800)
            targeter.requeue(cand, why)
            log_rest(why, mode="reply", persona=want, target_post=cand["post"]["post_id"])
            continue
        # nobody has them today, or their voice is parked or gone: any free voice may answer
        rec = candidate_voice(accounts.eligible, cand)
        if not rec:
            why = accounts.resting(t)
            targeter.requeue(cand, why or "no_voice")                  # keep it for the next slot
            if why:
                log_rest(why, mode="reply", target_post=cand["post"]["post_id"])
            return None
        return reply_job(cand, rec)
    return None


def pick_job(job, citizen, amp):
    """Greedy order, 2026-10-21 (todo/19): a citizen reply goes before the amplifier's own-thread jobs and its next
    post. On 21 Oct the amplifier went first and citizen-facing writes fell from 12-23/h to 1/h, though a reply to a
    citizen earns ~5x the citizen likes and replies of a thread reply. job: a queued reply-back, or None."""
    if job is None:
        job = citizen()
    if job is None and amp:                                  # own-thread replies, answers, reposts (due)
        job = amp.next_write_job()
    if job is None and amp and amp.amp_post_due():            # the next amplified original
        rec = amp.pick_author()
        if rec:
            job = dict(mode="post", rec=rec, frame=content.pick_frame(content.PERSONA_BY_KEY[rec["persona"]]),
                       amp=True, level=amp.choose_level())
    return job


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true", help="really register accounts and post (default: dry run)")
    ap.add_argument("--accounts", type=int, default=6, help=f"active accounts to grow to, one every 20-40 min (max {config.MAX_ACCOUNTS})")
    ap.add_argument("--hours", type=float, default=8)
    ap.add_argument("--per-min", type=float, default=1.0, help=f"max team writes per minute (hard max {config.MAX_PER_MIN}); the write budget's headers and the target "
                    f"queue set the real pace")
    ap.add_argument("--amplify", action="store_true", help="own-team amplification of our posts (todo/04); "
                    "touch AMPLIFY_OFF in the repo root to pause it without a restart")
    ap.add_argument("--boosters", type=int, default=0, help=f"with --amplify: like-only accounts to grow to, one every "
                    f"4-9 min (max {config.MAX_BOOSTERS})")
    ap.add_argument("--samples", type=int, default=0, help="dry run: stop after this many accepted drafts")
    ap.add_argument("--allow-qwen", action="store_true", help="fall back to the weak provided model when Gemini is out")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt for --live")
    ap.add_argument("--batch", type=int, default=0, help=f"draft up to N replies / second voices / persona posts per LLM "
                    f"call (2-{batch.MAX_SIZE}; 0 = one per call). docs/04-technical/llm-batching.md")
    ap.add_argument("--fixture", type=pathlib.Path, help="dry run: read Latest and Trending from this snapshot "
                    "(e.g. a copy of the box's data/latest_snapshot.json). Default data/feed_fixture.json, made once "
                    "from one live read. Dry runs never page the live feeds (todo/21 G1)")
    ap.add_argument("--no-humanize", action="store_true", help="send drafts exactly as the gate passed them, without "
                    "the personas' typing habits (humanize.py)")
    args = ap.parse_args()

    config.load_env()                                   # and the todo/31 SWAN_<NAME> overrides
    config.assigned_side()
    print("todo/31 stealth:", ", ".join(f"{n}={getattr(config, n)}" for n in config.STEALTH_ENV))
    code, owner = config.team_code(), config.operator()
    k = max(1, min(args.accounts, config.MAX_ACCOUNTS))
    per_min = max(0.1, min(args.per_min, config.MAX_PER_MIN))    # the headers bind first (write_gap)

    split = config.SPLIT_LOOP                           # todo/22: reader, drafter and writer threads
    social = ctn.LegitSocial()
    rsocial = ctn.LegitSocial() if split else social    # the reader's own client: X-RateLimit-* is per client
    gen = Generator(code, allow_qwen=args.allow_qwen)
    gen.on_park = lambda model, until, why: log({"act": "llm_park", "model": model, "why": why,
                                                 "until": dt.datetime.fromtimestamp(until, dt.timezone.utc).isoformat()})
    # the live bot is the one Latest reader and shares what it read (feeds.py); a dry run reads a saved fixture
    targeter = (Targeter(rsocial, log=log, snapshot=feeds.SNAPSHOT_FILE) if args.live else
                Targeter(feeds.FixtureFeeds(rsocial, feeds.fixture(rsocial, args.fixture)), log=log))
    accounts = Accounts(social, args.live)
    state = load_json(config.STATE_FILE, {})
    targeter.load(state.pop("targeter", None))          # read position, queue and funnel survive a restart (G3)
    for key, default in (("replied_posts", []), ("contacted", {}), ("engaged", {}), ("recent_texts", []), ("second_voice", []),
                         ("journalist_last", {}), ("modes", []), ("journalist_any", 0), ("recent_shapes", []),
                         ("theme_log", []), ("turns", {}), ("styles", {}), ("own_likes", [])):
        state.setdefault(key, default)
    ledger = themes.Ledger(state["theme_log"])          # the themes we sent, team-wide (saved with the state)
    if args.live:                                       # todo/31: the last day's writes count from the first minute,
        stealth.seed(accounts.records, state, config.ACTIONS_LOG)      # and the voices start at their own times
        stealth.stagger(accounts.voices())

    amp = None
    if args.amplify:
        amp = Amplifier(social, accounts, state, args.live, log, targeter=targeter, code=code, owner=owner,
                        boosters=args.boosters, save=lambda: save_state())

    # todo/22: what the threads share. mu guards state, queue, stats, the account records, the ledger and the amplifier
    # (the targeter has its own lock); only the writer saves files. The serial loop uses the same, uncontended.
    mu = threading.RLock()
    stop = threading.Event()             # SIGTERM/SIGINT (split loop), the watchdog, or the end of --hours/--samples
    woken = threading.Event()            # the reader found something new: the drafter stops waiting
    save_due = threading.Event()         # the reader asks the writer to save the state
    ready = []                           # drafts waiting for the writer, in the order chosen (at most DRAFT_AHEAD)
    inflight = [None]                    # the job the drafter is drafting now
    beats = {}                           # thread name -> time its loop last went round (status.json, the watchdog)
    workers = []
    rate_limited = []                    # times of 429s in the last hour (dashboard)
    write_rl = [None]                    # the write budget as our last write's headers reported it (todo/24)
    last_status = [0.0]

    def write_status():
        """data/status.json for the dashboard (todo/09), at most every 30 s. Counts and model names only, no secrets.
        The split loop adds each thread's heartbeat and the queues between them (todo/22)."""
        t = time.time()
        if not args.live or t - last_status[0] < 30:
            return
        last_status[0] = t
        rate_limited[:] = [x for x in rate_limited if t - x < 3600]
        recs = accounts.records
        limits = {w.name: w.silent_s for w in workers}
        try:                             # the dashboard must never stop the bot
            save_json(config.STATUS_FILE, dict(
                ts=now_iso(), per_min=per_min, llm=gen.status(), rate_limited_last_hour=len(rate_limited),
                write_budget=(dict(limit=write_rl[0].limit, remaining=write_rl[0].remaining, reset=write_rl[0].reset,
                                   margin=config.WRITE_MARGIN) if write_rl[0] else None),
                accounts=dict(live=len(accounts.active()), voices=len(accounts.voices()),
                              boosters=len(accounts.boosters()), used=len(recs),
                              suspended=sum(r.get("status") == "suspended" for r in recs)),
                # todo/31: per voice its writes, active hours, hidden posts and what holds it; the two-voice share
                stealth=stealth.metrics(accounts.voices(), accounts.hidden(), state, t,
                                        status=lambda r: accounts.status(r, t)),
                # todo/22: each thread's heartbeat (max_silent_s: the watchdog's limit) and the queues between them
                **(dict(loop="split", threads={name: dict(
                    last_run=dt.datetime.fromtimestamp(b, dt.timezone.utc).isoformat(), age_s=round(t - b),
                    **({"max_silent_s": limits[name]} if name in limits else {})) for name, b in sorted(beats.items())},
                    queue=dict(reply_backs=len(queue), candidates=len(targeter.candidates), drafts_ready=len(ready)),
                    **dict(zip(("oldest_waiting_s", "oldest_queued_s"), targeter.oldest_pending()))) if split else {})))
        except OSError as e:
            print("status.json not written:", e)

    def pause(seconds):
        """Sleep, but keep the amplifier's likes and views going meanwhile."""
        until = time.time() + seconds
        while True:
            beats["writer"] = time.time()
            write_status()
            if amp:
                with mu:
                    amp.tick()
            left = until - time.time()
            if left <= 0 or stop.is_set():
                return
            time.sleep(min(2.0, left))

    if args.live:
        lock = social.feed_lock()
        if lock.get("locked"):
            raise SystemExit(f"feed is locked: {lock.get('reason')}")
        print(f"LIVE: Vote No | owner {owner} | {len(accounts.active())} active accounts, growing to {k} "
              f"(one every 20-40 min) | up to {per_min}/min for {args.hours} h | LLM: {gen.describe()}"
              + (f" | AMPLIFY: {len(accounts.boosters())} boosters, growing to {amp.boosters_target}" if amp else "")
              + (" | split loop" if split else " | serial loop"))
        if not args.yes and input("Type GO to continue: ").strip() != "GO":
            raise SystemExit("aborted")
    else:
        print(f"DRY RUN: nothing will be registered or posted. LLM: {gen.describe()}")
        accounts.next_register = 0.0

    def held(mode=None):
        """Jobs chosen and not yet sent (split loop: drafting or waiting for the writer). choose() counts them as
        written, so draft-ahead makes the decisions the serial loop would."""
        jobs = [d["job"] for d in ready] + ([inflight[0]] if inflight[0] else [])
        return [j for j in jobs if mode is None or j["mode"] == mode]

    def save_state():
        if args.live:
            with mu:
                # pending reply-backs survive a restart (their notifications are already marked resolved)
                state["queue"] = [dict(username=j["rec"]["username"], target=j["target"], our_text=j["our_text"],
                                       tries=j.get("tries", 0)) for j in queue + held() if j["mode"] == "reply_back"]
                save_json(config.STATE_FILE, {**state, "targeter": targeter.dump()})

    end = time.time() + args.hours * 3600
    next_write = next_notif = 0.0
    queue, stats = [], {"accepted": 0, "rejected": {}, "by_mode": {}}
    by_user = {r["username"]: r for r in accounts.active()}
    for q in state.pop("queue", []):
        if q["username"] in by_user and (config.REPLY_BACK or config.REPLY_BACK_AMP):
            queue.append(dict(mode="reply_back", rec=by_user[q["username"]], target=q["target"],
                              our_text=q["our_text"], tries=q.get("tries", 0)))
    if queue:
        print(f"resumed {len(queue)} pending reply-back(s)")
    # --batch N: replies, second voices and plain persona posts are drafted N per LLM call into a pool (batch.Desk);
    # each draft goes out when its voice may next write. Everything else stays one draft per call.
    desk = batch.Desk(batch.Drafter(gen, size=args.batch, log=log), accounts.ready, log) if args.batch > 1 else None
    if desk:
        print(f"batched drafting: up to {desk.size} per LLM call")

    def desk_fill(jobs):
        for j in jobs:                                    # themes are drawn when queued; the budget is rechecked at send
            if j["mode"] in themes.MODES:
                pick_theme(j, ledger, j.setdefault("meta", {}))
        rejected = desk.fill(jobs, state["recent_texts"][-300:],
                             headline=targeter.headline if random.random() < 0.3 else None) or []
        for r in rejected:
            stats["rejected"][r["why"]] = stats["rejected"].get(r["why"], 0) + 1
            cand = r["job"].get("cand")
            if cand:                                          # a rejected reply target goes back, with a backoff
                targeter.requeue(cand, f"rejected:{r['why']}")

    def register():
        """Drip registration; a dry run registers fake accounts instantly so drafts can be read without waiting."""
        with mu:
            if args.live:
                accounts.maybe_register(k, code, owner)
                return
            while len(accounts.voices()) < k and len(accounts.records) < len(content.PERSONAS) + 50:
                accounts.next_register = 0.0
                before = len(accounts.records)
                accounts.maybe_register(k, code, owner)
                if len(accounts.records) == before:
                    break
            while amp and len(accounts.boosters()) < amp.boosters_target:
                amp.next_register = 0.0
                before = len(accounts.records)
                amp.maybe_register_booster()
                if len(accounts.records) == before:
                    break

    def our_ids():
        # No retirement by action count: accounts are lost through moderator-hidden posts, not actions
        # (scoring guide s3). Parking by hidden-post count is a TODO (TODO.md, "Hidden-post watch").
        return {r.get("account_id") for r in accounts.records if r.get("account_id")}

    def poll_reply_backs(session=None):
        """Citizens who replied to us or mentioned us, every NOTIF_EVERY_S (todo/20 G7): new jobs join the queue.
        session: the reader thread's own sessions (split loop). True when it queued any."""
        nonlocal next_notif
        if not (args.live and (config.REPLY_BACK or config.REPLY_BACK_AMP)) or time.time() < next_notif:
            return False
        with mu:
            roots = None if config.REPLY_BACK else {int(k) for k in (state.get("amp_posts") or {})}
            turns, replied = json.loads(json.dumps(state["turns"])), set(state["replied_posts"])
        jobs = reply_back_jobs(rsocial, accounts, targeter, roots=roots, turns=turns, replied=replied, session=session)
        with mu:
            queued = {j["target"]["post_id"] for j in queue + held("reply_back")}
            new = [j for j in jobs if j["target"]["post_id"] not in queued]
            queue.extend(new)
        next_notif = time.time() + config.NOTIF_EVERY_S
        return bool(new)

    def choose(t, ids):
        """The next job in the greedy order, and its pooled draft when --batch made one: (job, drafted, None), or
        (None, None, seconds to wait) when nothing is worth writing. The caller holds mu."""
        contacted = contacted_now(state["contacted"], held(), t)   # our voices per citizen this session (todo/21, /24)
        engaged = set(state["engaged"])
        pending = [j["mode"] for j in held()]               # chosen but not sent yet: counted as written (todo/22)
        job = None
        # the first reply-back whose voice may write: not within REPLY_BACK_GAP_S of its last write (don't double-post
        # from one account), and awake and under its caps (todo/31: it answers when it wakes; the rest go meanwhile)
        for j in queue:
            if j["rec"].get("last_write", 0) + REPLY_BACK_GAP_S > t:
                continue
            why = accounts.rest(j["rec"], t)
            if why:
                log_rest(why, mode="reply_back", persona=j["rec"]["persona"], target_post=j["target"]["post_id"])
                continue
            job = j
            queue.remove(j)
            job["frame"] = content.PERSONA_BY_KEY[job["rec"]["persona"]]["frames"][0]
            # the conversation goes on in the style of our reply they answered (todo/20 step 3)
            job["style"] = state["styles"].get(str(job["target"].get("reply_to_post_id")))
            break
        conv_arm = experiment.block("arm_conv")[1]      # todo/25 broadcast arm: a plain persona post ahead of citizens
        if (job is None and conv_arm == "broadcast" and (not amp or amp.paused())
                and "post" not in pending and t - state.get("last_post", 0) > config.CONV_POST_GAP_S):
            rec = accounts.eligible()
            if rec:
                job = dict(mode="post", rec=rec, frame=content.pick_frame(content.PERSONA_BY_KEY[rec["persona"]]))
        # batched drafting (--batch, not run live) keeps its replies after the amplifier, further down
        job = pick_job(job, (lambda: None) if desk else
                       (lambda: citizen_reply(targeter, accounts, ids, state["replied_posts"], contacted, engaged,
                                              state)), amp)
        drafted = None
        if job is None and amp and amp.priority_window():          # priority lane: the fresh thread gets the slots
            return None, None, WAIT_S["priority"]
        gone = lambda j: ((j.get("target") or {}).get("post_id") in state["replied_posts"]
                          or (j["mode"] == "reply"
                              and len(contacted.get(str(j["target"]["author_id"]), ())) >= config.SESSION_VOICES))
        second = config.SECOND_VOICE and not config.ONE_VOICE_PER_CITIZEN     # todo/31: one voice per citizen
        if job is None and desk and second:
            drafted = desk.take("second_voice", t, gone)
        if job is None and drafted is None and second:
            state["second_voice"] = [s for s in state["second_voice"] if t - s["due"] < 3600]   # stale after 1 h
            due = [s for s in state["second_voice"] if s["due"] <= t]
            picked = []
            for sv in due:
                rec = (accounts.assignable(sv["frame"], exclude={sv["first_persona"]} | desk.busy("second_voice", picked))
                       if desk else accounts.eligible(sv["frame"], exclude={sv["first_persona"]}))
                if not rec:
                    continue                                     # keep it until another persona is free
                state["second_voice"].remove(sv)
                if len(contacted.get(str(sv["author"]), set()) | {rec["persona"]}) > config.SESSION_VOICES:
                    continue                                     # the session cap (todo/21)
                try:
                    target = social.get_post(sv["post_id"])
                    thread = list(social.replies(sv["post_id"], limit=20))
                except ctn.APIError:
                    continue
                if len(thread) > 8 or any(r["author_id"] == target["author_id"] for r in thread):
                    continue                                     # busy thread, or they already answered us
                job = dict(mode="second_voice", rec=rec, target=target, frame=sv["frame"],
                           wants=sv.get("wants"), context=sv.get("context"), sv_delay=sv.get("sv_delay"))
                if not desk:
                    break
                picked.append(job)
                job = None
                if len(picked) >= desk.size:
                    break
            if picked:
                desk_fill(picked)
                drafted = desk.take("second_voice", t, gone)
        if job is None and drafted is None and desk:
            drafted = desk.take("reply", t, gone)
            if drafted is None:
                picked, authors = [], set()
                skip = set(state["replied_posts"]) | desk.pending_targets()
                while len(picked) < desk.size:
                    cand = targeter.next_target(ids, skip, contacted, engaged)
                    if not cand:
                        break
                    rec = candidate_voice(accounts.assignable, cand, exclude=desk.busy("reply", picked))
                    if not rec or cand["post"]["author_id"] in authors:
                        targeter.requeue(cand, "no_voice")                       # keep it for the next slot
                        break
                    authors.add(cand["post"]["author_id"])
                    picked.append(reply_job(cand, rec))
                if picked:
                    desk_fill(picked)
                    drafted = desk.take("reply", t, gone)
        if (job is None and drafted is None and t - state["journalist_any"] > config.JOURNALIST_GAP_S
                and "journalist" not in pending):
            jp = targeter.next_journalist(set(state["replied_posts"]), state["journalist_last"])
            if jp:
                frame, _ = classify(jp.get("body") or "")
                rec = accounts.eligible(frame or "F14_no_yes_but")
                if rec:
                    job = dict(mode="journalist", rec=rec, target=jp, frame=frame or "F14_no_yes_but")
        idle_post = t - state.get("last_post", 0) > config.IDLE_POST_GAP_S and "post" not in pending
        plain_posts = not amp or amp.paused()                    # amplified originals replace plain persona posts
        post_ok = plain_posts and ("post" not in (state["modes"] + pending)[-(config.POST_EVERY_N - 1):] or idle_post)
        if job is None and drafted is None and post_ok and desk:
            drafted = desk.take("post", t, gone)
            if drafted is None:
                picked = []
                while len(picked) < desk.size:
                    rec = accounts.assignable(exclude=desk.busy("post", picked))
                    if not rec:
                        break
                    picked.append(dict(mode="post", rec=rec,
                                       frame=content.pick_frame(content.PERSONA_BY_KEY[rec["persona"]])))
                if picked:
                    desk_fill(picked)
                    drafted = desk.take("post", t, gone)
        if drafted:
            job = drafted["job"]
        if job is None and post_ok and not desk:
            rec = accounts.eligible()
            if rec:
                job = dict(mode="post", rec=rec, frame=content.pick_frame(content.PERSONA_BY_KEY[rec["persona"]]))
        if job is None:
            # todo/31: no voice may write a post or a thread reply now (asleep or capped; citizens may still get the
            # rest of a voice's day): the writer just waits, and the skip says why the volume is lower
            why = accounts.resting(t, citizen=False)
            if why:
                log_rest(why, mode=None, voices=len(accounts.voices()))
            return None, None, WAIT_S["nothing"]
        if job.get("target") and not drafted:                 # todo/24: the strict near-duplicate comparison
            job["same_texts"] = same_target_texts(state.get("recent_sent", []), ready, job["target"])
        return job, drafted, None

    def draft(job, drafted, pulse_now):
        """Draft and check one job (batched drafts were checked when drafted). Returns what send() needs, or None
        when the light read skipped the target or every draft failed (then it is requeued or logged lost, G8)."""
        rec, mode, target = job["rec"], job["mode"], job.get("target")
        job.setdefault("draft_id", secrets.token_hex(4))     # ties this job's rejected drafts to its write
        persona = persona_of(rec)
        text = backend = user = repair = None
        if mode == "repost":
            text, backend = "", "none"
        elif drafted:
            text, backend = drafted["text"], drafted["backend"]
        else:
            with mu:                                 # drafts waiting to be sent count as sent (todo/22)
                recent_texts = state["recent_texts"] + [d["text"] for d in ready if d["text"]]
                recent_shapes = state["recent_shapes"] + [d["job"]["meta"]["shape"] for d in ready
                                                          if (d["job"].get("meta") or {}).get("shape")]
                persona, system, user = build_prompt(job, targeter, recent_shapes, pulse_now, recent_texts=recent_texts)
                if mode in quality.PERSONAL_KINDS and target and config.is_citizen(target.get("author_id")):
                    job["phrase_texts"] = citizen_texts(state.get("recent_sent", []), ready)     # todo/27

            def rejected(why, raw, backend, repaired):
                with mu:
                    stats["rejected"][why] = stats["rejected"].get(why, 0) + 1
                log({"act": "reject", "why": why, "mode": mode, "persona": persona["key"], "frame": job["frame"],
                     "backend": backend, "raw": raw, "repair": repaired, "draft_id": job["draft_id"],
                     "target_post": target and target["post_id"],
                     **{k: (job.get("meta") or {}).get(k) for k in REJECT_ARMS}})
                print(f"  rejected [{mode}] ({why}{', after repair' if repaired else ''}): {raw[:160]!r}")

            if (mode == "reply" and job["meta"].get("arm_conv") == "no_leaners" and
                    (job.get("target_class") or target_class(target.get("body") or "")) in config.CONV_SKIP_STANCES):
                job["read_skip"] = "arm_conv:lean_no"     # todo/25: a regex No-leaner costs no LLM call
            else:
                text, backend, repair = draft_checked(gen, job, system, user, recent_texts[-300:], rejected, ledger)
        if job.get("read_skip"):                      # the light read: hostile or not about the vote (final)
            if hasattr(targeter, "skip"):
                targeter.skip(target, f"light_read:{job['read_skip'][:60]}", job.get("source"))
            log({"act": "skip", "why": "arm_conv" if job["read_skip"].startswith("arm_conv:") else "read",
                 "detail": job["read_skip"][:200], "mode": mode, "block_id": (job.get("meta") or {}).get("block_id"),
                 "target_post": target["post_id"], "target_author": target["author_id"],
                 "target_class": target_class(target.get("body") or ""), "backend": backend,
                 "draft_id": job["draft_id"]})
            return None
        if not text and mode != "repost":
            # G8: a failed draft never silently drops a citizen: requeued, or logged as lost with its reason
            with mu:
                lose(targeter, queue, job, "no_model" if backend is None else
                     f"gate:{(job.get('meta') or {}).get('last_reject') or 'unknown'}")
            return None
        return dict(job=job, drafted=drafted, text=text, backend=backend, repair=repair, persona=persona)

    def send(d):
        """Send one checked draft and record it: the send-time checks, the write, then the state and the log."""
        nonlocal next_write
        job, drafted, text, backend, repair, persona = (d[k] for k in ("job", "drafted", "text", "backend", "repair",
                                                                       "persona"))
        rec, mode, target = job["rec"], job["mode"], job.get("target")
        with mu:
            if split:                                 # what changed while the draft waited (todo/22)
                gone = gone_at_send(job, state)
                if gone:
                    log({"act": "skip", "why": f"{gone}_at_send", "mode": mode, "persona": persona["key"],
                         "target_post": target and target["post_id"], "draft_id": job["draft_id"]})
                    if job.get("cand") and gone in ("session_cap", "voice_owner"):
                        targeter.requeue(job["cand"], "held")     # answered once their session is over / by their voice
                    return
            # todo/31: the voice fell asleep or reached a cap while its draft waited (both loops check it here)
            rest = accounts.rest(rec, citizen=mode in stealth.CITIZEN_MODES)
            if rest:
                log({"act": "skip", "why": f"{rest}_at_send", "mode": mode, "persona": persona["key"],
                     "target_post": target and target["post_id"], "draft_id": job["draft_id"]})
                if job.get("cand"):
                    targeter.requeue(job["cand"], "held")
                elif mode == "reply_back":
                    queue.append(job)                     # answered when its voice wakes
                return
            # the slogan budget again at send time (a pooled draft waited; another account may have used it since)
            thread = themes.thread_of(target) if target else None
            why = text and (ledger.send_problem(text, persona["key"], thread) or
                            (drafted and themes.draft_problem(text, job.get("theme"), mode, ledger)))
            if why:
                stats["rejected"][why] = stats["rejected"].get(why, 0) + 1
                log({"act": "reject", "why": why, "mode": mode, "persona": persona["key"], "frame": job["frame"],
                     "backend": backend, "raw": text, "draft_id": job["draft_id"], "at_send": True,
                     "target_post": target and target["post_id"],
                     **{k: (job.get("meta") or {}).get(k) for k in REJECT_ARMS}})
                print(f"  dropped at send [{mode}] ({why}): {text[:160]!r}")
                return
        clean, hand = text, []                    # the gate checked the clean draft; the persona types it out
        if text and not args.no_humanize:
            text, hand = humanize.apply(text, persona.get("hand", persona["key"]), mode)

        # ---- send ----
        post_id = None
        if args.live:
            def write(acc):
                if mode == "post":
                    return acc.post(text)
                if mode == "repost":
                    return acc.repost(target["post_id"])
                return acc.reply(target["post_id"], text)

            acc = accounts.session(rec)
            try:
                r = write(acc)
            except ctn.APIError as e:
                if e.status != 401:
                    raise
                acc = accounts.relogin(rec)
                r = write(acc)
            post_id = r["post_id"]
            write_rl[0] = acc.rate_limit             # the team-wide write budget, as this answer reported it
            # a citizen who talks back to us: follow them from that persona (separate follow budget)
            if mode == "reply_back" and target["author_id"] not in rec.setdefault("followed", []):
                try:
                    acc.follow(target["author_id"])
                    rec["followed"].append(target["author_id"])
                    log({"act": "follow", "username": rec["username"], "account_id": target["author_id"]})
                except ctn.APIError as e:
                    print("follow:", e.status, e.message)
        with mu:
            rec["last_write"], rec["writes"] = time.time(), rec.get("writes", 0) + 1
            stealth.on_write(rec, rec["last_write"])            # todo/31: its day's writes and its next gap
            if target:
                stealth.record(state, target, persona["key"], mode)     # todo/31: this voice has the citizen today
            accounts.save()
            if args.live:
                next_write = time.time() + write_gap(write_rl[0], per_min)      # todo/24: from the headers
            stats["accepted"] += 1
            stats["by_mode"][mode] = stats["by_mode"].get(mode, 0) + 1
            state["modes"] = (state["modes"] + [mode])[-20:]

            if target:
                state["replied_posts"] = (state["replied_posts"] + [target["post_id"]])[-5000:]
                targeter.answered(target, mode)          # the funnel (todo/21 G12)
            if mode in ("reply", "reply_back", "second_voice"):   # the session cap counts our voices (todo/21)
                contact(state["contacted"], target["author_id"], persona["key"])
            if mode == "reply_back":                      # a conversation turn (todo/20: TURNS_PER_SESSION)
                t_now, who = time.time(), str(target["author_id"])
                state["turns"] = {k: v for k, v in state["turns"].items() if t_now - v[-1] < config.TURN_SESSION_S}
                state["turns"][who] = state["turns"].get(who, []) + [t_now]
            if mode == "reply_back":                      # they're talking to us: no extra persona joins in
                state["second_voice"] = [s for s in state["second_voice"] if s["author"] != target["author_id"]]
                state["engaged"][str(target["author_id"])] = time.time()     # ENGAGED_BONUS on their next post
            if (mode == "reply" and config.SECOND_VOICE and job.get("arm") != "firm_yes"     # no pile-on on a firm Yes
                    and job.get("group") != "off_topic"):                 # nor a referendum angle on their own topic
                job["sv_delay"] = experiment.alternate("sv_delay", list(config.SECOND_VOICE_ARMS))    # todo/20 step 7
                state["second_voice"].append(dict(due=time.time() + random.uniform(*config.SECOND_VOICE_ARMS[job["sv_delay"]]),
                                                  sv_delay=job["sv_delay"],
                                                  post_id=target["post_id"], author=target["author_id"],
                                                  frame=second_frame(job["frame"]),
                                                  first_persona=persona["key"], wants=job.get("wants"),
                                                  context=job.get("context")))
            if mode == "reply" and config.OWN_LIKE_ARM:            # todo/20 step 8: one own like, alternate replies
                job["own_like"] = experiment.alternate("own_like", config.OWN_LIKE_VARIANTS)
                if job["own_like"]:
                    state["own_likes"].append(dict(post_id=post_id, due=time.time() + random.uniform(*config.OWN_LIKE_DELAY_S),
                                                   author=rec["username"], draft_id=job["draft_id"]))
            if mode in ("reply", "reply_back") and job.get("style") and post_id:     # reply-backs keep the style
                state["styles"][str(post_id)] = job["style"]
                state["styles"] = dict(list(state["styles"].items())[-3000:])
            if mode == "post":
                state["last_post"] = time.time()
                if job.get("amp"):
                    amp.on_post(post_id, rec, text, job["frame"], job["level"])
            if mode == "thread" and amp:
                amp.on_thread_sent(job, post_id, text)
            if mode == "journalist":
                state["journalist_any"] = time.time()
                state["journalist_last"][str(target["author_id"])] = time.time()
            if text:
                state["recent_texts"] = (state["recent_texts"] + [clean])[-300:]
                if target:                            # todo/24: who it went to (quality.near_duplicate)
                    state["recent_sent"] = (state.get("recent_sent", []) + [
                        [target["author_id"], thread_root(target), clean]])[-300:]
                ledger.record(clean, persona["key"], job.get("theme"), thread or post_id, mode)
            meta = job.get("meta") or {}
            if mode == "post" and meta.get("shape"):
                state["recent_shapes"] = (state["recent_shapes"] + [meta["shape"]])[-30:]
            save_state()
        log({"act": mode, "live": args.live, "post_id": post_id, "username": rec["username"],
             "account_id": rec.get("account_id"), "owner": rec.get("owner", owner), "persona": persona["key"],
             "frame": job["frame"], "backend": backend, "source": job.get("source"),
             "target_post": target and target["post_id"], "target_author": target and target["author_id"],
             "target_text": target and (target.get("body") or "")[:300], "context": job.get("context"),
             "parent_post": target and target.get("reply_to_post_id"),       # what the target was answering
             "parent_text": (job.get("our_text") or "")[:300] or None, "draft_id": job["draft_id"],
             "text": text, "clean": clean if hand else None, "hand": hand or None, "amp_level": job.get("level"),
             "amp_post": job.get("amp_post"), "style": job.get("style"), "repair": repair,
             **{k: meta.get(k) for k in ("shape", "hook", "voice", "pillar", "tag", "now", "storyline", "opener",
                                         "pulse", "pulse_news", "theme", "theme_level_drawn", "slogan")},
             **{k: meta.get(k) for k in ARMS}, **experiment_fields(target, job.get("target_class")),
             **{k: job.get(k) for k in ("priority", "arm", "engaged")},                   # todo/21
             "length": len(clean or ""), **{k: meta.get(k) for k in ("llm_calls", "repairs", "fixes")},  # G9
             # todo/20: the reply style arm and the light read; todo/21's arm and priority, next to target_class
             "arm": job.get("arm"), "priority": job.get("priority"), "group": job.get("group"),
             "net": job.get("net"),                       # todo/23: the arm it counts against (engaged + off_topic)
             "sv_delay": job.get("sv_delay"),
             "own_like": job.get("own_like"),
             "frame_in": job.get("frame_in"),
             **{k: meta.get(k) for k in ("read_ok", "read_stance", "read_doubt", "read_frame")},
             "catchphrase": content.catchphrase_in(text), "identity": job.get("identity"),
             "messenger_match": bool(job.get("identity")) and persona["key"] in messengers(job.get("identity")),
             "thread": threading.current_thread().name,                                   # todo/22: the writer
             **({k: drafted[k] for k in ("batch_id", "batch_pos", "batch_size")} if drafted else {})})
        where = ""
        if target:
            ctx = f" [under: {job['context'][:60]!r}]" if job.get("context") else ""
            where = f"\n    -> #{target['post_id']} (author {target['author_id']}){ctx}: {(target.get('body') or '')[:200]!r}"
        via = f"|{drafted['batch_id']} #{drafted['batch_pos'] + 1}/{drafted['batch_size']}" if drafted else ""
        tags = "|".join(str(meta[k]) for k in ("voice", "shape") if meta.get(k))
        print(f"[{mode}|{job['frame']}|{tags}|{backend}{via}] {persona['name']}{where}\n    {text}\n")

    def handle(e, job, wait):
        """What every loop does with an API, LLM or fact-desk error (wait: that loop's sleep). The rest is raised."""
        if isinstance(e, ctn.RateLimited):
            rate_limited.append(time.time())
            wait((e.retry_after or 30) + 1)
        elif isinstance(e, ctn.APIError):
            print("API error", e.status, e.message)
            msg = (e.message or "").lower()
            if e.status == 403 and "suspended" in msg and job:
                with mu:
                    job["rec"]["status"] = "suspended"
                    accounts.save()
                log({"act": "suspended", "username": job["rec"]["username"]})
            elif e.status == 403 and "locked" in msg:
                wait(300)
            wait(10)
        elif isinstance(e, openai.APIError):
            print("LLM error", type(e).__name__, str(e)[:120])
            wait(20)
        elif isinstance(e, content.AllPaused):        # the fact desk paused every frame: wait for a review
            print(e)
            wait(300)
        else:
            raise e

    LOOP_ERRORS = (ctn.APIError, openai.APIError, content.AllPaused)

    # ---- the serial loop (config.SPLIT_LOOP off): read, draft and write in turn, as before todo/22 ----
    def serial_loop():
        while time.time() < end and not (args.samples and stats["accepted"] >= args.samples):
            job = None
            write_status()
            try:
                register()
                if not accounts.voices():
                    pause(WAIT_S["no_voice"])
                    continue
                ids = our_ids()
                if targeter.refresh():
                    save_state()
                own_likes(state, accounts, args.live)
                pulse_now = pulse.update(state, targeter, ids, gen, log)
                if amp:
                    amp.tick()
                poll_reply_backs()

                wait = next_write - time.time()
                if wait > 0:
                    pause(min(wait, 30))
                    continue
                if gen.next_available_in() > 0 and not args.allow_qwen:
                    print(f"no Gemini model available; waiting {gen.next_available_in() / 60:.0f} min")
                    pause(min(gen.next_available_in() + 1, 600))
                    continue
                job, drafted, wait = choose(time.time(), ids)
                if job is None:
                    pause(wait)
                    continue
                d = draft(job, drafted, pulse_now)
                if d:
                    send(d)
            except LOOP_ERRORS as e:
                handle(e, job, pause)
            except KeyboardInterrupt:
                if job and job.get("mode") == "reply_back" and job not in queue:
                    queue.insert(0, job)                  # stopped mid-draft: keep the citizen's reply for next run
                break
        save_state()

    # ---- the split loop (todo/22): the reader and the drafter work ahead; the writer only sends ----
    reader_sessions = Sessions(rsocial)

    def reader_step():
        """Read targets and reply-backs (the only feed reader), then sleep until the next one is due."""
        try:
            if targeter.refresh():
                save_due.set()
                woken.set()
            if poll_reply_backs(session=reader_sessions.get):
                woken.set()
        except ctn.APIError as e:
            handle(e, None, stop.wait)
        due = targeter.next_refresh
        if args.live and (config.REPLY_BACK or config.REPLY_BACK_AMP):
            due = min(due, next_notif)
        stop.wait(min(60.0, max(1.0, due - time.time())))

    def drafter_step():
        """Choose the next job and draft it while the writer waits for its slot (at most DRAFT_AHEAD waiting)."""
        if len(ready) >= config.DRAFT_AHEAD:
            stop.wait(IDLE_S)
            return
        if not accounts.voices():
            stop.wait(WAIT_S["no_voice"])
            return
        job = d = None
        try:
            ids = our_ids()
            with mu:
                kept = {k: state[k] for k in ("pulse", "pulse_next") if k in state}
            pulse_now = pulse.update(kept, targeter, ids, gen, log)       # the LLM call happens outside the lock
            with mu:
                state.update(kept)
            if gen.next_available_in() > 0 and not args.allow_qwen:
                print(f"no Gemini model available; waiting {gen.next_available_in() / 60:.0f} min")
                stop.wait(min(gen.next_available_in() + 1, 600))
                return
            woken.clear()
            with mu:
                job, drafted, wait = choose(time.time(), ids)
                if job:
                    accounts.reserved.add(job["rec"]["persona"])        # no second draft for this voice meanwhile
                    inflight[0] = job
            if job is None:
                woken.wait(wait)                                      # or until the reader finds something
                return
            d = draft(job, drafted, pulse_now)
        except LOOP_ERRORS as e:
            handle(e, job, stop.wait)
        finally:
            with mu:
                inflight[0] = None
                if d:
                    ready.append(d)
                elif job:
                    accounts.reserved.discard(job["rec"]["persona"])

    def check_workers():
        """The watchdog (todo/22): a thread that died or went silent stops the bot. It logs, alerts like BOT CRASHED,
        saves the state and exits 1, so systemd restarts it. Never runs on without its reader or drafter."""
        if stop.is_set():
            return
        for w in workers:
            why = w.problem()
            if why:
                log({"act": "thread_died", "thread": w.name, "why": why})
                print(f"watchdog: {w.name} {why}")
                if args.live:
                    alert(f"BOT THREAD DIED: {w.name} ({why}) at {experiment.git_sha()}; state saved, exiting so "
                          f"systemd restarts it. Logs: journalctl -u swan-bot -n 50")
                shutdown()
                raise SystemExit(1)

    def shutdown():
        """Stop the threads, put back what was chosen and not sent (a reply-back stays in the saved queue, a citizen
        goes back to the targeter's queue), and save. A send in progress has finished: only the writer sends."""
        stop.set()
        woken.set()
        for w in workers:
            w.join(timeout=JOIN_S)
        with mu:
            for j in held():
                if j.get("cand"):
                    targeter.requeue(j["cand"], "held")
                accounts.reserved.discard(j["rec"]["persona"])
        save_state()

    def write_loop():
        while time.time() < end and not stop.is_set() and not (args.samples and stats["accepted"] >= args.samples):
            beats["writer"] = time.time()
            check_workers()
            write_status()
            job = None
            try:
                register()
                if save_due.is_set():
                    save_due.clear()
                    save_state()
                with mu:
                    own_likes(state, accounts, args.live)
                    if amp:
                        amp.tick()
                wait = next_write - time.time()
                if wait > 0:
                    pause(min(wait, 30))
                    continue
                with mu:                     # the first draft whose voice may write now, in the order chosen
                    t = time.time()
                    d = next((d for d in ready if voice_wait(d["job"], accounts, args.live, t) <= 0), None)
                    if d:
                        ready.remove(d)
                if d is None:
                    pause(IDLE_S)
                    continue
                job = d["job"]
                send(d)
            except LOOP_ERRORS as e:
                handle(e, job, pause)
            finally:
                if job:
                    with mu:
                        accounts.reserved.discard(job["rec"]["persona"])

    if not split:
        serial_loop()
    else:
        def on_signal(signum, frame):
            print(f"signal {signum}: stopping after the current step")
            stop.set()
            woken.set()

        old = {s: signal.signal(s, on_signal) for s in (signal.SIGTERM, signal.SIGINT)}
        try:
            workers += [Worker("reader", reader_step, stop, beats, config.READER_SILENT_S),
                        Worker("drafter", drafter_step, stop, beats, config.DRAFTER_SILENT_S)]
            for w in workers:
                w.start()
            write_loop()
            shutdown()
        finally:
            for s, h in old.items():
                signal.signal(s, h)
    print("done:", json.dumps({**stats, "llm_calls": gen.calls, **({"pool_left": len(desk.pool)} if desk else {})}))

if __name__ == "__main__":
    main()
