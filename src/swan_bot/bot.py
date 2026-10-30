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
import hashlib
import http.client
import json
import os
import pathlib
import random
import re
import secrets
import signal
import socket
import ssl
import subprocess
import threading
import time
import traceback
import urllib.error

import openai
import capturethenarrative as ctn
from . import batch, config, content, engage, experiment, feeds, flip, humanize, memory, mention, news, pool_runner, pulse, quality, register, room, stealth, themes, watch
from . import batch, config, content, engage, experiment, feeds, humanize, mention, pool_runner, pulse, quality, stealth, themes, watch
from .amplify import Amplifier
from .analysis import ts_of
from .llm import Generator
from .targeting import YES_REASON, agrees, Targeter, classify, contact, messengers, room_stance, sessions, soft_yes, stance, target_class

AGREE_STANCES = ("lean_no", "firm_no")      # todo/32: a light read that says they lean or stand No agrees with us
REPLY_BACK_JOBS = 10          # reply-back jobs read per poll (todo/20 G7; was 3)
REPLY_BACK_GAP_S = 60         # a reply-back waits this long after its voice's last write (not the 4-min gap)


def hot_handover_now(times, t):
    """Hot mode: True when a 403 "suspended" at time t may hand over to the next spare with no pause. The account is marked
    suspended, so the next write goes to another account and nothing is retried; the 10 s pause only cost the team about
    10 s of writes per switch (24-25 Oct: 11-31 s from the 403 to the next voice's first write). `times` (the caller's
    list) keeps the 403s of the last HOT_HANDOVER_WINDOW_S; after HOT_HANDOVER_FAST of them (a run of spares that were
    dead already) the pause comes back."""
    times[:] = [x for x in times if t - x < config.HOT_HANDOVER_WINDOW_S] + [t]
    return bool(config.HOT_VOICES) and len(times) <= config.HOT_HANDOVER_FAST


STUCK_N = 5                   # failed writes in a row (401/403, not "suspended" or "locked") that make a voice stuck (~1 min)
STUCK_WAIT_S = 60             # once stuck and alerted, the writer tries again this often (was every 10 s: known-bad calls)


class StuckWrites:
    """Writes that keep failing with a 401 or 403 that is neither "suspended" nor "locked" (25 Oct uptime check): handle()
    waited 10 s and tried the same voice again, forever, with no log row and no alert, and in hot mode that is every write.
    A spell is the failed writes since the last one that went through. In hot mode a voice's STUCK_N-th failure in a spell
    benches it ("bench": Accounts.benched, for this run only, nothing saved) so the next spare writes; if a voice fails the
    same way after that, it is not the voice (the team's clearance, the platform): "alert", once a spell, and nothing else
    is switched. Outside hot mode the spell's STUCK_N-th failure is "alert"."""

    def __init__(self, n=None):
        self.n_max = STUCK_N if n is None else n
        self.ok()

    def ok(self):
        """A write went through: the spell is over."""
        self.n, self.by, self.benched, self.told = 0, {}, [], False

    def fail(self, username, hot):
        """One more failed write by `username`. Returns "bench", "alert" or None."""
        self.n += 1
        self.by[username] = self.by.get(username, 0) + 1
        if hot and self.by[username] == self.n_max and not self.benched:
            self.benched.append(username)
            return "bench"
        if not self.told and (self.by[username] if hot else self.n) >= self.n_max:
            self.told = True
            return "alert"
        return None


def hot_track(accounts, hot):
    """Hot-writer bookkeeping on the records (the caller holds mu): rec["hot_from"] = {at, w0} when a voice becomes the writer, and "w"
    (its writes as the hot writer) once it is suspended. Returns the stop-rule alert text when the last HOT_STOP_N hot
    writers averaged under HOT_STOP_WRITES, else None. A voice with no hot_from (the writer before this) is not counted."""
    by, changed = {r["username"]: r for r in accounts.records}, False
    rec = by.get(hot["active"]) if hot["active"] else None
    if rec is not None and not rec.get("hot_from"):
        rec["hot_from"], changed = dict(at=now_iso(), w0=rec.get("writes", 0)), True
    for u in hot["lost"]:
        r = by.get(u)
        if r and r.get("hot_from") and "w" not in r["hot_from"]:
            r["hot_from"]["w"], changed = max(0, r.get("writes", 0) - r["hot_from"].get("w0", 0)), True
    if changed:
        accounts.save()
    done = sorted((r["hot_from"] for r in accounts.records if ((r.get("hot_from") or {}).get("w") or 0) > 0),    # a spare
                  key=lambda h: h["at"])                                                                      # suspended unused never wrote: not counted
    last = [h["w"] for h in done[-config.HOT_STOP_N:]]
    if len(last) == config.HOT_STOP_N and sum(last) / len(last) < config.HOT_STOP_WRITES:
        return (f"HOT STOP RULE: the last {len(last)} hot writers lasted {', '.join(map(str, last))} writes (mean "
                f"{sum(last) / len(last):.0f}, under the {config.HOT_STOP_WRITES} the account budget needs at 3 a minute). "
                f"Nothing was changed. To go back to the many-voice pool: unset SWAN_HOT_VOICES and restart.")
    return None


def reply_back_gap():
    """REPLY_BACK_GAP_S, except in hot mode: the one voice writes every ~20 s, so a 60 s rule would starve every reply-back
    (24 Oct: 19 queued and none sent in 5 h of hot mode, against 4 to 11 an hour before)."""
    return config.HOT_GAP_S if config.HOT_VOICES else REPLY_BACK_GAP_S
WAIT_S = dict(no_voice=30, nothing=45, priority=15)   # a loop with nothing to do waits this long (s)
IDLE_S = 1.0                  # split loop: the writer looks for a ready draft this often (s)
PULSE_POLL_S = 30.0           # split loop: the pulse thread looks whether a refresh is due at least this often (s)
JOIN_S = 10.0                 # split loop: on a stop, how long the writer waits for the other threads (s)
# No model answered a draft (every free model parked, the paid ones kept back for amplified posts or over budget): the
# drafter pauses this long before choosing again. 2026-10-23: without it, 27,858 jobs were lost as no_model in 3 h
# (10,782 in one 10-minute window): next_available_in() was 0 while a paid model was skipped but not parked (fixed the
# same day: llm.no_model_wait counts the budget and the reserve; runbook "No model").
NO_MODEL_PAUSE_S = 60
NO_MODEL_ALERT_N, NO_MODEL_ALERT_S = 5, 600           # this many no-model drafts within 10 min: alert once, then "recovered"
# 2026-10-23 (later): the pause alone left the job dropped (journalist, post, second voice, thread) and the log at a row
# per attempt (580,780 rows in 8 h). Now a no-model draft is deferred, not lost (bot.defer), and the attempts are one
# episode in the log (act "no_model": a start row, one row per NO_MODEL_LOG_EVERY_S with the count, an end row).
NO_MODEL_PAUSE_MAX_S = 600    # a pause set from what the LLM chain knows (llm.no_model_wait) is at most this long
NO_MODEL_TRIES = 10           # attempts in one episode before the pause stretches to NO_MODEL_LONG_PAUSE_S (logged once)
NO_MODEL_LONG_PAUSE_S = 180
NO_MODEL_LOG_EVERY_S = 30     # at most one "no_model" row per this many seconds (plus the start and end rows)
NO_MODEL_RECOVER_S = 30       # a model has answered this long without a new miss: the episode is over (no flapping rows)
NO_MODEL_ALERT_AGE_S = 300    # or an episode this old: alert once even if few drafts were tried (long waits between them)


def model_wait(gen):
    """Seconds until some model could answer a draft (0: one can now). A draft may spend the amplified-post reserve
    (draft_checked asks again with priority), so priority=True. A gen without no_model_wait (a test fake) answers
    through next_available_in."""
    fn = getattr(gen, "no_model_wait", None)
    return fn(priority=True) if fn else gen.next_available_in()


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
        self._portal_next = 0.0      # todo/40: the next time sync_portal reads data/portal.json
        self.reserved = set()        # personas with a draft not sent yet (split loop): not picked for another
        self.benched = set()         # hot mode: usernames whose writes are stuck (StuckWrites), skipped until a restart
        created = [dt.datetime.fromisoformat(r["created"]).timestamp() for r in self.records
                   if r.get("created") and r.get("role", "voice") != "booster"]
        if created:                      # a restart must not register straight after the last registration
            self.next_register = max(created) + random.uniform(*config.REGISTER_GAP_S)

    _SAVE_LOCK = threading.RLock()          # todo/38: the pool thread saves too; two saves never write the .tmp at once

    def save(self):
        if self.live:
            with Accounts._SAVE_LOCK:
                save_json(config.ACCOUNTS_FILE, self.records, private=True)

    def ramp_ok(self, rec, t):
        """todo/38: a voice the pool has just activated or converted (rec["ramp"] = {from, until, start}) is ready with a
        chance that rises linearly from `start` (0.25) to 1 at `until`: light first days. A voice with no ramp: always."""
        ramp = rec.get("ramp")
        if config.HOT_VOICES or not ramp or t >= ramp.get("until", 0):     # hot mode: one voice at the full rate, no light days
            return True
        span = max(1.0, ramp["until"] - ramp.get("from", t))
        p = ramp.get("start", 0.25) + (1 - ramp.get("start", 0.25)) * min(1.0, max(0.0, (t - ramp.get("from", t)) / span))
        return random.random() < p

    def active(self):
        return [r for r in self.records if r.get("status", "active") == "active"]

    def usable(self):
        """Active accounts the bot may act as: all but swan_blue's reporter (it holds its own session)."""
        reporter = config.blue_reporter(self.records) if self.live else None
        return [r for r in self.active() if r is not reporter]

    def voices(self):
        """Persona accounts that write. Boosters (role 'booster') only view and like.
        Hot mode (config.HOT_VOICES): just the first named voice that is still active, if any; the others wait as spares,
        and a suspended one drops out of this list on the same call that sees its record change."""
        voices = [r for r in self.active() if r.get("role", "voice") != "booster"]
        if config.HOT_VOICES:
            by_name = {r["username"]: r for r in voices if r["username"] not in self.benched}
            return next(([by_name[u]] for u in self.hot_roster() if u in by_name), [])
        return voices

    def hot_roster(self):
        """Hot mode's order of use: the names in config.HOT_VOICES, then the voices the pool activated or converted since,
        oldest activation first (so the refill joins the end and never jumps the queue). Suspended names stay in the list."""
        named = set(config.HOT_VOICES)
        auto = sorted((r for r in self.records if r.get("role", "voice") != "booster" and r.get("username") not in named
                       and (r.get("pool") or {}).get("act") in ("activate", "convert")),
                      key=lambda r: (r["pool"].get("at") or "", r.get("username")))
        return list(config.HOT_VOICES) + [r["username"] for r in auto]

    def hot(self):
        """Hot mode's live roster for the status file and logs: {active, spares, lost}, or None when it is off."""
        if not config.HOT_VOICES:
            return None
        roster = self.hot_roster()
        status = {r["username"]: r.get("status", "active") for r in self.records}
        live = [u for u in roster if status.get(u) == "active" and u not in self.benched]
        by = {r["username"]: r for r in self.records}
        mine = lambda u: u in config.HOT_VOICES or (by.get(u) or {}).get("hot_from")     # old pool voices that never wrote hot are not "lost"
        return dict(active=live[0] if live else None, spares=live[1:],
                    lost=[u for u in roster if status.get(u) == "suspended" and mine(u)],
                    missing=[u for u in config.HOT_VOICES if u not in status])

    def boosters(self):
        """Like-only accounts, less the one swan_blue reports from (config.blue_reporter)."""
        reporter = config.blue_reporter(self.records) if self.live else None
        return [r for r in self.active() if r.get("role") == "booster" and r is not reporter]

    def maybe_register(self, k, code, owner):
        """Drip registration: at most one new account per call, 20-40 min apart, never more than MAX_ACCOUNTS.
        todo/38: not at all while config.POOL_LIVE (the pool worker is then the only registrar)."""
        if self.live and (config.POOL_LIVE or config.HOT_VOICES):     # hot mode: only the pool refills (SWAN_HOT_POOL_LIVE)
            return
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

    def mark_suspended(self, rec, at=None):
        """The one way a record becomes suspended: a 403 "suspended" on a write (bot.handle) or a like (amplify), or the
        portal's own list (sync_portal). Keeps the first suspended_at (the pool's loss rate reads it) and saves.
        at: an ISO time when the platform did it (the portal's), else now. The caller logs it."""
        rec["status"] = "suspended"
        rec.setdefault("suspended_at", at or now_iso())
        self.save()

    def sync_portal(self, log, t=None):
        """todo/40: mark every active record the portal's suspension list names (data/portal.json, written by the dashboard
        poller; watch.portal_suspended), at most every config.PORTAL_SYNC_S. A match needs the record's username AND
        account id to equal the portal's: a similar name, or an id with another name, marks nothing. Returns the
        usernames newly marked. The caller holds the bot's lock. Live only."""
        t = time.time() if t is None else t
        if not (self.live and config.PORTAL_SYNC) or t < self._portal_next:
            return []
        self._portal_next = t + config.PORTAL_SYNC_S
        found = watch.portal_suspended(now=t)
        marked = []
        for rec in self.records:
            ident = rec.get("account_id")
            hit = found.get((rec.get("username"), ident)) if isinstance(ident, int) and not isinstance(ident, bool) else None
            if not hit or rec.get("status", "active") != "active":
                continue
            when = dt.datetime.fromtimestamp(min(ts_of(hit["ts"]), t), dt.timezone.utc).isoformat()    # never in the future
            self.mark_suspended(rec, at=when)
            log({"act": "suspended", "username": rec["username"], "account_id": ident, "via": "portal",
                 "portal_ts": hit["ts"], "why": hit["why"]})
            marked.append(rec["username"])
        return marked

    def young(self, t=None):
        """todo/40: the personas of voices in their first config.NEW_VOICE_NO_POST_H hours of voice life (stealth.new_voice).
        They write replies only: the callers that pick a voice for a persona post, an amplified post or a thread reply
        leave these out (exclude=)."""
        t = time.time() if t is None else t
        return {r["persona"] for r in self.voices() if stealth.new_voice(r, t)}

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

    def n_writers(self):
        """Voices able to write: active persona accounts that are not parked (the N of stealth.plan, todo/38)."""
        return len([r for r in self.voices() if not self.parked(r)])

    def _sched(self, t):
        """todo/38: True when the pool scheduler picks (live bot, config.POOL_SCHEDULER). Refreshes its level, life profiles
        and rate controller from the voices able to write; a life drawn for a voice that had none is saved once."""
        if not (self.live and config.POOL_SCHEDULER):
            return False
        if stealth.refresh([r for r in self.voices() if not self.parked(r)], t):
            self.save()
        return True

    def _choose(self, cands, sched, t):
        """The voice that writes next out of the candidates: the weighted pick of the pool scheduler, else (and in dry
        runs, or with POOL_SCHEDULER off) the one that wrote longest ago."""
        if sched and cands:
            return stealth.pick(cands, t)
        return min(cands, key=lambda r: r.get("last_write", 0)) if cands else None

    def assignable(self, frame=None, exclude=(), prefer=(), citizen=False):
        """Like eligible(), but the voice may still be in its gap: for batched drafts that wait in the pool."""
        t = time.time()
        sched = self._sched(t)
        free = [r for r in self.voices() if r["persona"] not in exclude and r["persona"] not in self.reserved
                and not self.parked(r) and not self.rest(r, t, citizen) and self.ramp_ok(r, t)]
        mine = [r for r in free if r["persona"] in prefer]
        if mine:
            free = mine
        elif frame:
            free = [r for r in free if frame in content.PERSONA_BY_KEY[r["persona"]]["frames"]] or free
        return self._choose(free, sched, t)

    def eligible(self, frame=None, exclude=(), gap=None, prefer=(), citizen=False):
        """The voice that wrote longest ago among those free now: a shared-identity messenger (prefer) first,
        then personas whose home frames include the frame. todo/31: not asleep or capped (citizen: the write is to a
        citizen, so the end of the daily budget is open to it), and an ordinary write (gap None) waits for the
        voice's jittered gap; a repost (gap given) only for its own."""
        t = time.time()
        sched = self._sched(t)
        jitter = gap is None
        if gap is None or not self.live:                         # dry runs rotate personas without waiting
            gap = config.ACCOUNT_MIN_GAP_S if self.live else 0
        ready = [r for r in self.voices() if r.get("last_write", 0) + gap <= t and r["persona"] not in exclude
                 and r["persona"] not in self.reserved and not self.parked(r)
                 and (not jitter or self.gap_ok(r, t)) and not self.rest(r, t, citizen) and self.ramp_ok(r, t)]
        if sched and not ready and jitter and not exclude and not prefer:
            stealth.note_empty(t)               # todo/38: nobody ready although voices exist: the rate controller reads it
        mine = [r for r in ready if r["persona"] in prefer]
        if mine:
            ready = mine
        elif frame:
            fit = [r for r in ready if frame in content.PERSONA_BY_KEY[r["persona"]]["frames"]]
            ready = fit or ready
        return self._choose(ready, sched, t)

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


# A dropped connection, a TLS EOF or a timeout on one request: the platform or the network blinked. The client library
# retries only 429s, so these reach the worker. 2026-10-23: one SSLEOFError in the reader exited the whole bot, twice in
# 50 min (01:01 and 01:49 UTC), each time a restart and a gap in writes.
TRANSIENT_NET = (urllib.error.URLError, ssl.SSLError, socket.timeout, ConnectionError, http.client.HTTPException)
NET_RETRY_S = 15                    # wait before the next round after a transient network error
NET_MAX_IN_ROW = 8                  # this many failed rounds in a row (~2 min) is an outage: let the watchdog restart


class Worker(threading.Thread):
    """One of the split loop's threads: runs step() until stop is set, noting each round in beats (todo/22). Any other
    exception ends it and is kept for the writer's watchdog, which stops the bot (problem()). A transient network
    error (TRANSIENT_NET) only costs the round: it is logged, the thread waits NET_RETRY_S and goes on."""

    def __init__(self, name, step, stop, beats, silent_s, critical=True):
        super().__init__(name=name, daemon=True)
        self.step, self.stop, self.beats, self.silent_s = step, stop, beats, silent_s
        self.critical = critical             # False: the watchdog alerts once when it fails, but the bot runs on without it
        self.reported = False
        self.error = None
        self.net_errors = 0

    def run(self):
        try:
            while not self.stop.is_set():
                self.beats[self.name] = time.time()
                try:
                    self.step()
                    self.net_errors = 0
                except TRANSIENT_NET as e:
                    self.net_errors += 1
                    if self.net_errors >= NET_MAX_IN_ROW:
                        raise
                    print(f"{self.name}: network error, retrying in {NET_RETRY_S} s "
                          f"({self.net_errors}/{NET_MAX_IN_ROW}): {type(e).__name__}: {e}"[:300])
                    self.stop.wait(NET_RETRY_S)
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
    gap = (reply_back_gap() if mode == "reply_back" else config.REPOST_MIN_GAP_S if mode in ("repost", "thread_answer")
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
    out = [text for a, _, text in sent if config.writes_to_citizen(a)]
    out += [d["text"] for d in ready if d.get("text") and config.writes_to_citizen((d["job"].get("target") or {}).get("author_id"))]
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


def clashes_with_ready(text, mode, ready):
    """Several drafters (23 Oct): does a fresh draft repeat one that finished while it was under way? The gate compared it
    with the texts known when it started; this is the same near-duplicate and same-opening test against `ready`."""
    if not text or mode == "repost":
        return False
    others = [d["text"] for d in ready if d.get("text")]
    if quality.near_duplicate(quality.strip_tag(text), mode, others):
        return True
    opening = lambda t: " ".join(re.findall(r"[a-z']+", t.lower())[:4])
    return bool(opening(text)) and any(opening(o) == opening(text) for o in others[-30:])


def thread_depth(social, post, cap):
    """How many posts sit above `post` in its thread, counted up to `cap` (one read per level, stopping there)."""
    depth, parent = 0, post.get("reply_to_post_id")
    while parent and depth < cap:
        depth += 1
        parent = social.get_post(parent).get("reply_to_post_id")
    return depth


def depth_cap(post_id):
    """(arm, cap) for a citizen's reply: how deep a thread we still answer in. THREAD_DEPTH_TEST off: ("off", 8). On: half the
    posts (a sha256 of their id, the same after a re-poll or a restart) answer to THREAD_DEPTH_TEST_CAP ("deep"), the rest
    to THREAD_MAX_DEPTH ("base")."""
    if not config.THREAD_DEPTH_TEST:
        return "off", config.THREAD_MAX_DEPTH
    odd = int(hashlib.sha256(f"depth_cap:{post_id}".encode()).hexdigest()[:8], 16) % 2
    return ("deep", config.THREAD_DEPTH_TEST_CAP) if odd else ("base", config.THREAD_MAX_DEPTH)


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
        if accounts.parked(rec):                  # a parked voice answers nobody (its notifications stay unresolved)
            continue
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
                if not config.writes_to_citizen(theirs.get("author_id")):     # todo/48: the extra arm's citizens too, when on
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
                ours, depth = None, None
                arm, cap = depth_cap(theirs["post_id"])
                if not skip and theirs.get("reply_to_post_id"):
                    ours = social.get_post(theirs["reply_to_post_id"])
                    # posts above the citizen's reply, read up to the deeper cap so the log has it (a value at the cap
                    # means "at least"); the arm's cap decides
                    depth = thread_depth(social, ours, max(cap, config.THREAD_MAX_DEPTH)) + 1
                    if depth >= cap:
                        skip = "deep_thread"
                if skip:
                    if skip not in ("not_citizen", "not_our_thread"):
                        log({"act": "skip", "why": skip, "mode": "reply_back", "target_post": theirs["post_id"],
                             "target_author": theirs.get("author_id"), "username": rec["username"],
                             "depth": depth, "depth_arm": arm})
                else:
                    jobs.append(dict(mode="reply_back", rec=rec, target=theirs, tries=0, via=n["kind"],
                                     our_text=(ours or {}).get("body") or "", depth=depth, depth_arm=arm))
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
        "block_id", "arm_conv", "arm_eng", "fresh", "agree", "arm_npc", "npc_block",     # todo/48: arm_npc with NPC_EXTRA_ARM
        "arm_style", "colour", "lean", "lean_shape",                                       # todo/50: the prompt fixes
        "rb_open",                                                                         # todo/51: the reply-back opener
        "news", "flip",                                                                    # 29 Oct: today's news (news.py), the flip (flip.py)
        "flip_fear", "flip_lift", "worries")                                               # todo/52: the fear dial, the room's lift, the pulse's worries (its id)
REJECT_ARMS = ("shape", "voice", "lever", "concede", "rebuttal", "ask_kind", "length_band", "reply_mode", "beat", "close",
               "pulse", "theme", "theme_level", "arm_style", "lean_shape", "rb_open")


def queue_arm(t=None, late_sends=()):
    """The send-queue arm of this 3 h block (config.QUEUE_ARMS), "base" off a switchback. `shallow` falls back to `fresh`
    while QUEUE_GUARD_N sends in the last QUEUE_GUARD_S ran late (late_sends: their times)."""
    t = time.time() if t is None else t
    arm = experiment.block("arm_queue", t)[1] or "base"
    if arm == "shallow" and sum(1 for x in late_sends if t - x < config.QUEUE_GUARD_S) >= config.QUEUE_GUARD_N:
        return "fresh"
    return arm


def draft_ahead(arm):
    """Drafts chosen and not sent (ready + inflight) allowed in this queue arm (at least 1: an .env 0 can't stop drafting)."""
    return max(1, min(config.DRAFT_AHEAD, config.QUEUE_SHALLOW_AHEAD) if arm == "shallow" else config.DRAFT_AHEAD)


def jit_hold(next_write, now, arm, lead=None):
    """todo/58: True while a drafter should wait before choosing its next job: a shallow block, JIT_LEAD_S on, and the
    writer's next slot more than `lead` seconds away, so the job chosen is the freshest post just before its slot. Never
    before the first send (next_write 0), in other arms (fresh is the late-send guard's fill-ahead), or past the slot."""
    lead = config.JIT_LEAD_S if lead is None else lead
    return bool(lead) and arm == "shallow" and next_write > 0 and next_write - now > lead


def target_made(d):
    """When the post a ready draft answers was written (unix s); 0 when unknown, so it goes last among the fresh."""
    try:
        return dt.datetime.fromisoformat((((d["job"].get("target") or {}).get("created_at")) or "").replace("Z", "+00:00")).timestamp()
    except (ValueError, KeyError):
        return 0.0


def pick_ready(ready, may_write, arm, now):
    """The ready draft the writer sends next, or None. base: the first whose voice may write. fresh, shallow: the one
    whose target is newest, except that a draft ready for more than QUEUE_MAX_WAIT_S goes first (oldest first)."""
    able = [d for d in ready if may_write(d)]
    if not able or arm == "base":
        return able[0] if able else None
    stale = [d for d in able if now - d.get("ready_at", now) > config.QUEUE_MAX_WAIT_S]
    return stale[0] if stale else max(able, key=target_made)


def stage_times(job, target):
    """Where a reply's time goes, for the dashboard (unix seconds): the citizen's post written (its own created_at),
    the job chosen (t_pick), its draft checked (t_drafted) and now, the send. Drafts made ahead by the desk were
    drafted before t_pick, so their drafting stage reads ~0 (drafted_ahead)."""
    try:
        made = dt.datetime.fromisoformat(((target or {}).get("created_at") or "").replace("Z", "+00:00")).timestamp()
    except ValueError:
        made = None
    return dict(t_made=made and round(made, 1), t_pick=job.get("t_pick") and round(job["t_pick"], 1),
                t_drafted=job.get("t_drafted") and round(job["t_drafted"], 1), t_sent=round(time.time(), 1),
                drafted_ahead=bool(job.get("drafted_ahead")) or None)


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


def context_is_news(job):
    """True when the context a job carries was written by a paper or an organiser (ids up to config.OFFICIAL_MAX_ID);
    a neighbour's or another team's post is not news (content.context_line). Without the parent's author: only the
    papers' own threads (source "news") are."""
    author = job.get("parent_author")
    return job.get("source") == "news" if author is None else author <= config.OFFICIAL_MAX_ID


STYLE_MODES = ("reply", "reply_back", "second_voice")      # todo/50: the citizen-facing kinds arm_style is drawn for


def style_memory(state, job):
    """job["memory"] for a citizen-facing draft (todo/50): what the voice has used up today, its latest texts, and our
    history with the citizen. Read under mu, from bot.py's state (memory.py has the layout)."""
    rec, target = job["rec"], job.get("target") or {}
    return dict(spent=memory.spent_items(state, rec["username"]), voice_texts=memory.voice_texts(state, rec["username"]),
                history=memory.history(state, target["author_id"]) if target.get("author_id") is not None else (0, []))


def style_context(job, persona, meta):
    """The fixes for this draft (todo/50), or None: base block, STYLE_FIXES off, or not a citizen-facing kind.
    Sets meta["arm_style"] for the citizen-facing kinds and job["fixes"] (the gate and the hand read it)."""
    if job["mode"] not in STYLE_MODES:
        return None
    meta["arm_style"] = memory.arm()
    job["fixes"] = meta["arm_style"] == "fixes"
    if not job["fixes"]:
        return None
    rec, mem = job["rec"], job.get("memory") or {}
    body = (job.get("target") or {}).get("body") or ""
    reg = register.read(body)
    parent = job.get("parent_author")
    me = dict(persona, username=rec.get("username"))
    return dict(colour=memory.colour(), spent=mem.get("spent") or (), history=mem.get("history") or (0, []),
                me=rec.get("username"), register=reg, addressed=reg["addressed"],
                addressed_me=register.is_me(reg["addressed"], me), personal=register.personal(body),
                own_parent=parent is not None and parent == rec.get("account_id"))


def flip_choice(job, body, meta):
    """29 Oct (Marc): the flip for this reply (flip.choose), or None: never off-topic, never to a citizen who already
    opposes the pass. Its key is logged as meta["flip"], with the fear dial (flip_fear) and the items the room lifted
    (flip_lift, todo/52), so the panel can join a move to what we said."""
    if job.get("style") == "off_topic" or content.opposes_pass(body):
        return None
    choice = flip.choose(body)
    if choice:
        meta.update(flip=flip.key(choice), flip_fear=config.FLIP_FEAR, flip_lift=",".join(choice["lifted"]) or None)
    return choice


def news_story(job, body, meta, rng=random):
    """29 Oct (Marc): the news story for this reply (news.pick), or None. NEWS_SHARE of first replies and reply-backs,
    every turnout reply (NEWS_TURNOUT_SHARE), never an off-topic one. Its key is logged as meta["news"]."""
    if not config.NEWS_ON or job.get("style") == "off_topic":
        return None
    turnout = job.get("group") == "turnout"
    if rng.random() >= (config.NEWS_TURNOUT_SHARE if turnout else config.NEWS_SHARE):
        return None
    story = news.pick(body, rng=rng, turnout=turnout)
    if story:
        meta["news"] = story["key"]
    return story


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
    spent = quality.spent_phrases(job.get("phrase_texts"), body)     # budgeted words the gate would reject right now
    if mode in config.CONV_MODES:                                 # todo/25: the conversion arm of this 2 h block
        block_id, arm = experiment.block("arm_conv")
        meta.update(arm_conv=arm or "base", **({"block_id": block_id} if block_id else {}))
        block_id, arm = experiment.block("arm_eng")                # todo/33: the engagement arm of this 2 h block
        meta.update(arm_eng=arm or "base", **({"block_id": block_id} if block_id else {}))
        if config.NPC_EXTRA_ARM:                                   # todo/48: the extra-citizens arm, its own 3 h blocks
            block_id, arm = experiment.block("arm_npc")
            meta.update(arm_npc=arm or "base", npc_block=block_id)
    if mode == "reply" and job.get("group") == "off_topic":      # todo/23: on their topic, no read, no theme
        job["style"], job["read"] = "off_topic", False
    elif mode == "reply":                # todo/20: the style arm in turn (the firm-Yes arm concedes first) and the read
        job["style"] = ("mirror_concede" if job.get("arm") == "firm_yes" else
                        experiment.alternate("style", config.REPLY_STYLES))
        job["read"] = config.LIGHT_READ
    fx = style_context(job, persona, meta)                         # todo/50: a fixes block of arm_style, else None
    lean = bool(fx and config.LEAN_PROMPT and mode == "reply" and job.get("style") == "current")
    # four beats, not about the vote, or the lean prompt (todo/50: no theme line): no theme
    mirror = job.get("style") in ("mirror_concede", "off_topic") or lean
    if lean:
        job["theme"] = None
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
        if lean:                                                  # todo/50 fix 5
            user = content.lean_reply_prompt(body, job["frame"], job.get("wants"), job.get("context"), meta=meta,
                                             persona=persona, read=job["read"], hint=job["frame_in"],
                                             news=context_is_news(job), fixes=fx)
        else:
            user = content.reply_prompt(body, job["frame"], job.get("wants"), job.get("context"), meta=meta,
                                        persona=persona, theme=theme, style=job["style"], read=job["read"],
                                        hint=job["frame_in"], recent=recent_texts, spent=spent,
                                        news=context_is_news(job), fixes=fx)
        if meta.get("arm_conv") == "fresh_facts" and job["style"] != "off_topic":     # todo/25: news first
            fresh = content.fresh_line(body, meta)
            user = user.replace("\n\nFirst read them", f" {fresh}\n\nFirst read them", 1) \
                if job["read"] else f"{user} {fresh}"
        if content.group_style(job):                              # todo/23's groups: one line of guidance
            user = user.replace("\n\nFirst read them", f" {content.group_style(job)}\n\nFirst read them", 1) \
                if job["read"] else f"{user} {content.group_style(job)}"
        fl = flip_choice(job, body, meta)                         # 29 Oct: the fear behind a Yes, flipped (flip.py)
        line = content.flip_line(fl) if fl else None
        if line and line[1:] not in user:                         # (the rebuttal slot carries it, unless the frame took it)
            user = user.replace("\n\nFirst read them", f" {line}\n\nFirst read them", 1) if job["read"] else f"{user} {line}"
        if fl and (pulse_now or {}).get("worries"):               # todo/52 WS6: what the room is saying, beside the flip
            meta["worries"] = pulse_now.get("id")
            line = content.worries_line(content.worry_for(pulse_now["worries"], body))
            user = user.replace("\n\nFirst read them", f" {line}\n\nFirst read them", 1) if job["read"] else f"{user} {line}"
        story = None if fl else news_story(job, body, meta)       # 29 Oct: today's news (news.py)
        if story:
            line = content.news_line(story)
            user = user.replace("\n\nFirst read them", f" {line}\n\nFirst read them", 1) if job["read"] else f"{user} {line}"
    elif mode == "second_voice":
        user = content.second_voice_prompt(body, job["frame"], job.get("wants"), job.get("context"), meta=meta,
                                           persona=persona, recent=recent_texts, spent=spent,
                                           news=job.get("news", True))
    elif mode == "journalist":
        user = content.journalist_prompt(target["author_id"], body, meta=meta, persona=persona)
    else:
        user = content.reply_back_prompt(job["our_text"], body, style=job.get("style"), spent=spent, fixes=fx, meta=meta)
        meta["style"] = job.get("style")
        if meta.get("arm_conv") == "agree_close":                 # todo/32: close on our vote when they agree
            meta["agree"] = agrees(body)
            closing = content.reply_back_prompt(job["our_text"], body, style=job.get("style"), agree_close=True)
            job["gate_policy"] = {quality.PHRASE_PREFIX: dict(fix=False, redraft=user)}   # over budget: the base prompt
            if meta["agree"]:
                meta["agree_by"], user = "keywords", closing
            else:                                                 # the light read: their stance, in the same call
                job["read"], job["on_read"] = True, dict(stances=AGREE_STANCES, redraft=closing, base=user)
                user += content.reply_back_read_block()
        if meta.get("arm_conv") == "fresh_facts":                 # todo/25: news first
            user = f"{user} {content.fresh_line(body, meta)}".rstrip()
        fl = None if job.get("read") else flip_choice(job, body, meta)     # 29 Oct: the fear behind a Yes, flipped
        if fl:                                                    # (a condition, as in first replies: the post must show it)
            user = f"{user} {content.conditional_rebuttal(content.flip_line(fl))}"
        story = None if fl else news_story(job, body, meta)       # 29 Oct: today's news (news.py)
        if story and not job.get("read"):
            user = f"{user} {content.news_line(story)}"
    if job.get("mention") and mode == "reply" and job.get("style") != "off_topic":     # todo/46: name one other citizen
        line = mention.prompt_line(job["mention"])
        user = user.replace("\n\nFirst read them", f" {line}\n\nFirst read them", 1) if job.get("read") else f"{user} {line}"
    if lean:
        system = content.lean_system_prompt(persona, job["frame"], meta=meta, fixes=fx,
                                            pulse=pulse_now if parts else None, pulse_parts=parts)
    else:
        system = content.system_prompt(persona, job["frame"], meta=meta, pulse=pulse_now if parts else None,
                                       pulse_parts=parts, mode=mode,
                                       fixes=dict(colour=fx["colour"], spent=fx["spent"]) if fx else None)
    if job.get("mention") and mode == "reply" and job.get("style") != "off_topic":     # the style rule bans @mentions: Haiku obeyed it
        system = system.replace(" @mentions,", "", 1)                                    # 1 of 44 drafts wrote the handle (25 Oct)
    return persona, system, user


# Drafts at 0.7 keep to their shape and length better; own-thread reactions keep 0.9 for variety (todo/14)
TEMPERATURE = {"thread": 0.9, "thread_answer": 0.9}
# A 70-word post is ~100 tokens. Flash-lite spends no thinking tokens out of the cap (2026-10-21: max_tokens=120
# finished "stop" at 73), so this only stops a runaway answer
MAX_TOKENS = 600


def repair_prompt(user, raw, note):
    return (f"{user}\n\nYour draft was:\n<<<{raw}>>>\nFix only this: {note} Change as little as you can and keep "
            f"the rest. Output only the fixed text.")


THEME_REASONS = {"unplanned_slogan", "slogan_missing", "theme_without_reason", "theme_echo_repeat"}   # themes.draft_problem


def gate_rule(job, why):
    """The job's gate_policy for a reject reason: {prefix of the reason: {fix: False to skip the code fix, redraft: the
    prompt to draft again on}}. Policies are per job, so one kind of reply can keep a fix that would strip another's
    point (todo/32: the closing vote line is what the cut-the-vote fix removes); {} when the job has none for it."""
    return next((r for k, r in (job.get("gate_policy") or {}).items() if why.startswith(k)), {})


def gate(raw, job, user, recent_texts, ledger=None):
    """(text, why, fixes): quality.check, the code fixes for what it rejects (quality.fix, at most 3, no LLM call),
    then the theme check. text is None when the draft still fails; fixes names the fixes that were applied."""
    mode, meta = job["mode"], job.get("meta") or {}
    kw = dict(prompt_text=user, known_caps=job.get("system_caps") or (),
              target_text=(job.get("target") or {}).get("body") or "",
              wants=job.get("wants") or (), closing_question=meta.get("closing_question", True),
              specific=job.get("group") != "off_topic", same=job.get("same_texts") or (),
              phrase_texts=job.get("phrase_texts"),
              phrase_exempt=("concede_open",) if job.get("style") == "mirror_concede" else (),   # firm_yes concedes
              mention=(job.get("mention") or {}).get("username"),                                # todo/46: the one handle allowed
              **(dict(voice_texts=(job.get("memory") or {}).get("voice_texts"), echo_open=True,  # todo/50: a fixes block
                      floor=config.FIXES_REPLY_FLOOR) if job.get("fixes") else {}))
    draft, fixes = raw, []
    text, why = quality.check(draft, mode, recent_texts, **kw)
    while why and len(fixes) < 3:
        if not gate_rule(job, why).get("fix", True):
            break                           # a job's gate_policy can leave a reject to draft_checked (todo/32)
        fixed = quality.fix(draft, why, mode, recent=recent_texts, same=job.get("same_texts") or ())
        if not fixed or fixed == draft:
            break
        fixes.append(why.split("_")[0] if why.startswith(("length_", "unapproved_")) else why)
        draft = fixed
        text, why = quality.check(draft, mode, recent_texts, **kw)
    job["gate_draft"] = draft               # what the last check judged: a repair goes from this text and this reason
    theme_why = text and themes.draft_problem(text, job.get("theme"), mode, ledger)
    if theme_why:
        return None, theme_why, fixes
    return text, why, fixes


def high_value(job):
    """A draft worth the premium model (config.PREMIUM_MODELS): an amplified post, a journalist, a reply-back, or a
    reply to a citizen who can still move (config.PREMIUM_CLASSES) or who has answered us before."""
    if job.get("amp") or job["mode"] in ("journalist", "reply_back"):
        return True
    return job["mode"] == "reply" and (job.get("target_class") in config.PREMIUM_CLASSES or bool(job.get("engaged")))


def draft_models(job, gen):
    """(models, ordered) for a draft. Amplified posts: AMP_MODELS (chain order). Replies to citizens (STRONG_MODES,
    todo/24): REPLY_MODELS in that order, then the rest of the chain, never REPLY_NEVER (ordered). Thread one-liners:
    the free models, then the paid REPLY_MODELS as the last resort (ordered). Anything else: None, the whole chain."""
    chain = [m for _, m in getattr(gen, "chain", ())]
    full_chain = chain                                          # the premium reply models are in the chain file only to
    chain = [m for m in chain if m not in config.PREMIUM_REPLY_MODELS]   # be named below; never a fallback (llm.Generator)
    if job.get("amp"):                                          # our best content: Sonnet leads (AMP_MODELS order)
        return config.AMP_MODELS, True
    if job["mode"] == "journalist":
        order = list(config.PREMIUM_MODELS) + list(config.REPLY_MODELS) + chain
        return [m for m in dict.fromkeys(order) if m not in config.REPLY_NEVER and (m in chain)], True
    if job["mode"] in config.STRONG_MODES:                      # where minds change
        lead = list(config.PREMIUM_MODELS) if high_value(job) else []
        if job.get("fixes") and high_value(job) and job["mode"] in config.PREMIUM_REPLY_MODES:   # 28 Oct: Sonnet on the
            lead += [m for m in config.PREMIUM_REPLY_MODELS if m in full_chain]                 # fixes prompt; todo/51: not reply-backs
        replies = list(config.REPLY_MODELS)
        if config.LEAD_HAIKU_SHARE and "lead" not in job:      # 24 Oct: a random lead, so hide rates compare cleanly
            job["lead"] = config.HAIKU if random.random() < config.LEAD_HAIKU_SHARE else replies[0]
        if job.get("lead") in replies:
            replies.remove(job["lead"])
            replies.insert(0, job["lead"])
        order = lead + replies + [m for m in chain if m not in replies]
        return [m for m in dict.fromkeys(order) if m not in config.REPLY_NEVER], True
    if job["mode"] in config.CHEAP_MODES:                       # one-liners: free models first, paid ones as backup
        free = [m for m in chain if m not in config.LLM_PRICES]  # 23 Oct: the free quotas are gone by ~14:30 Sydney and
        paid = [m for m in config.REPLY_MODELS if m in config.LLM_PRICES and m in chain and m not in config.REPLY_NEVER]
        return free + paid, True                                # these drafts then found no model; Kimi, then Haiku (never Sonnet)
    return None, False


def complete_in_order(gen, system, prompt, models, **kw):
    """gen.complete on each model in turn (the chain's own order would put flash-lite before Kimi): the first answer,
    or (None, None). A parked or over-budget model returns at once, so this costs no extra time. The real Generator
    spreads load when the lead model is busy (llm.Generator.complete_in_order, 23 Oct)."""
    if hasattr(gen, "complete_in_order"):
        return gen.complete_in_order(system, prompt, models, **kw)
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
    job["system_caps"] = quality.caps_in(system)               # the voice's own people are not invented names
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

        def ask():
            if ordered:                                         # replies: the whole order is already the fallback
                raw, backend = complete_in_order(gen, system, prompt, use or models, **kw)
                if raw is not None and getattr(gen, "overflowed_from", None):
                    meta["overflowed_from"] = gen.overflowed_from   # the lead model was busy: who took the call (audit)
            else:
                raw, backend = gen.complete(system, prompt, models=use or models, **kw)
            if raw is None and use and not ordered:             # out of quota: the usual chain
                raw, backend = gen.complete(system, prompt, **kw)
            return raw, backend
        raw, backend = ask()
        if raw is None and not kw["priority"]:                  # nothing answered: the amplified-post reserve pays for this
            kw["priority"] = True                               # draft rather than lose it (23 Oct: no replies for hours)
            raw, backend = ask()
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
            if r["skip"] and prompt is user and not job.get("on_read"):    # a citizen who answered us is never skipped
                job["read_skip"] = r["skip"]
                return None, backend, None
            draft = r["reply"] or ""
            on_read = job.get("on_read")
            if on_read and prompt is user and r["stance"] in on_read["stances"]:    # todo/32: they agree: close on our vote
                job["read"] = False                   # the closing prompt answers in plain text
                meta.update(agree=True, agree_by="read")
                user = prompt = on_read["redraft"]
                continue
        text, why, fixes = gate(draft, job, user, recent_texts, ledger)
        if text:
            meta["fixes"] = fixes
            return text, backend, repair
        failed[backend] = failed.get(backend, 0) + 1
        meta["last_reject"] = why
        if on_reject:
            on_reject(why, raw, backend, repair)
        redraft = gate_rule(job, why).get("redraft")
        if redraft and user != redraft:                         # todo/32: a fresh draft on the job's other prompt
            user = prompt = redraft
            repair, meta["redrafted"] = None, why
            continue
        draft = job.pop("gate_draft", draft)                    # the draft after the code fixes, the one `why` is about
        note = (themes.repair_note(why, job.get("theme")) if why in THEME_REASONS else
                quality.repair_note(why, draft, mode, meta.get("tag"), recent=recent_texts,
                                    target_text=(job.get("target") or {}).get("body") or "",
                                    wants=job.get("wants") or (), same=job.get("same_texts") or (),
                                    phrase_texts=job.get("phrase_texts")))
        if note and job.get("read"):
            note += " Output only the fixed reply text, not JSON."
        prompt, repair = (repair_prompt(user, draft, note), why) if note else (user, None)
        meta["repairs"] += bool(note)
    return None, backend, repair


REPLY_BACK_TRIES = 3          # a citizen who answered us is drafted for this many slots before they're lost (G8)


def defer(targeter, queue, job):
    """No model could draft this job (23 Oct): put it back as it was, the same for every mode, so it is neither
    dropped nor counted as a try; the drafter's no-model pause spaces the next attempt. A reply goes back to the
    targeter (no try counted, see Targeter.requeue); a reply-back to the front of the queue; a second voice or a thread
    job through job["defer"] (set where it was picked: it hands back what the pick consumed); a post or journalist
    reply consumed nothing (their selection state changes only after a send). True when put back."""
    mode = job["mode"]
    if mode == "reply":
        if job.get("cand") and hasattr(targeter, "requeue"):
            targeter.requeue(job["cand"], "no_model")
            return True
        return False
    if mode == "reply_back":
        queue.insert(0, job)
        return True
    undo = job.get("defer")
    if callable(undo):
        undo()
        return True
    return mode in ("post", "journalist")


def lose(targeter, queue, job, why):
    """A job whose draft failed (G8/G12). why "no_model" (nothing could answer: not the job's fault) puts the job back
    for every mode (defer) and logs nothing here: the drafter's episode row counts it. Otherwise a reply to a citizen
    goes back to the targeter (its requeue backs off and logs the expiry); a reply-back goes to the back of the queue,
    REPLY_BACK_TRIES times; everything else, and anything that can't be put back, is logged as lost with the reason."""
    mode, target = job["mode"], job.get("target") or {}
    if why == "no_model" and defer(targeter, queue, job):
        return "deferred"
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


ENG_PER_TICK = 3              # follows and likes sent in one writer tick: the writer must not stall on them
_ROUTE_RL = {}                # "follow" / "like" -> the X-RateLimit-* its last answer reported (engage.budget_wait)


def engage_actions(state, accounts, live, now=None):
    """todo/33: the follows and likes due in state["eng_queue"] (engage.plan queued them with a reply). Each goes from the
    persona that replied, after the gates in engage: not asleep or parked, not followed already, at most
    ENG_FOLLOWS_PER_DAY follows a day and ENG_FOLLOW_GAP_S between two, no like and follow for the same citizen within
    ENG_PAIR_GAP_S, and the route's own budget (30/min, team-wide) from its last X-RateLimit-* headers, never a
    hard-coded pace. A gap, the budget or a 429 puts the action back (ENG_RETRIES times); anything else drops it.
    Every action is logged with the persona, its owner and the cell. Writes are off unless live."""
    now = time.time() if now is None else now
    queue = state.setdefault("eng_queue", [])
    last = state.setdefault("eng_last", {})
    for k in [k for k, v in last.items() if now - max(v.values()) > 3600]:
        del last[k]
    sent = 0
    for x in [x for x in queue if x["due"] <= now]:
        if sent >= ENG_PER_TICK:
            break
        queue.remove(x)
        kind, citizen = x["kind"], x["citizen"]
        entry = {"act": kind, "live": live, "username": x["username"], "citizen_id": citizen, "post_id": x["post_id"],
                 "eng_cell": x["cell"], "why": x.get("why") or x["mode"], "purpose": f"eng_{kind}",
                 "draft_id": x.get("draft_id")}
        if kind == "follow":
            entry.pop("post_id")
            entry["account_id"] = citizen              # what older follow rows called it: the account followed
        rec = next((r for r in accounts.voices() if r["username"] == x["username"]), None)

        def drop(why, **kw):
            log({"act": "eng_skip", "kind": kind, "why": why, "username": x["username"], "citizen_id": citizen,
                 "eng_cell": x["cell"], **kw})

        def later(why, wait=0.0):
            if x.get("tries", 0) < config.ENG_RETRIES:
                queue.append(dict(x, due=now + max(config.ENG_RETRY_S, wait), tries=x.get("tries", 0) + 1))
            else:
                drop(f"{why}_gave_up")

        if rec is None or accounts.parked(rec):
            drop("parked" if rec else "gone")
            continue
        if live and stealth.asleep(rec["persona"], now):
            drop("asleep")                               # a person asleep does not follow anyone
            continue
        why = engage.follow_block(rec, citizen, last, now) if kind == "follow" else engage.like_block(citizen, last, now)
        wait = engage.budget_wait(_ROUTE_RL.get(kind))
        if not why and wait > 0:
            why = "budget"
        if why in engage.GAP_REASONS:
            later(why, wait)
            continue
        if why:
            drop(why)
            continue
        entry.update(voice_id=rec.get("account_id"), owner=rec.get("owner"), role=rec.get("role", "voice"))
        if live:
            def act(acc):
                if kind == "like":
                    acc.view(x["post_id"])
                    acc.like(x["post_id"])
                else:
                    acc.follow(citizen)
            try:
                acc = accounts.session(rec)
                try:
                    act(acc)
                except ctn.APIError as e:
                    if e.status != 401:
                        raise
                    acc = accounts.relogin(rec)
                    act(acc)
            except ctn.RateLimited as e:
                later("rate_limited", getattr(e, "retry_after", 0) or 0)
                continue
            except ctn.APIError as e:
                log({**entry, "act": f"{kind}_failed", "error": e.status})
                continue
            _ROUTE_RL[kind] = acc.rate_limit
            if kind == "follow":
                engage.note_follow(rec, citizen, now)
                accounts.save()
        last.setdefault(str(citizen), {})[kind] = now
        sent += 1
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
    suspended card (rec["converted"]["style_of"]), so it doesn't read as the old account back (todo/31).
    A variant (rec["variant"], variants.py, todo/38) is the card read-only overlaid: its own name, age, hand (a dict
    humanize.apply takes), people and details, on a copy; the card's profile text is not copied anywhere else."""
    if rec.get("variant"):
        from . import variants
        return variants.persona(rec)
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
    if config.POOL_LIVE and not (args.live and split):
        # the pool worker runs only in the live split loop; without it the old registrars would be off AND nobody registering
        print("POOL_LIVE needs --live and the split loop: ignoring it, the old registrars run as before")
        config.POOL_LIVE = False
    social = ctn.LegitSocial()
    rsocial = ctn.LegitSocial() if split else social    # the reader's own client: X-RateLimit-* is per client
    gen = Generator(code, allow_qwen=args.allow_qwen)
    gen.park_file = config.DATA / "llm_parks.json"          # quota parks survive a deploy's restart
    gen.load_parks()
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
                         ("theme_log", []), ("turns", {}), ("styles", {}), ("own_likes", []), ("eng_queue", []),
                         ("eng_last", {})):
        state.setdefault(key, default)
    ledger = themes.Ledger(state["theme_log"])          # the themes we sent, team-wide (saved with the state)
    if args.live:                                       # todo/31: the last day's writes count from the first minute,
        stealth.seed(accounts.records, state, config.ACTIONS_LOG)      # and the voices start at their own times
        stealth.stagger(accounts.voices())
        hours = room.load()                             # todo/52: the room's counts survive a restart; the first start
        seeded = 0 if hours else room.seed(config.ACTIONS_LOG, lambda text: room_stance(text, target_class(text)))
        print(f"room: {hours} hours of counts back from {room.STATE_NAME}" + (f", {seeded} answered posts from the log" if seeded else ""))

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
    ready = []                           # drafts waiting for the writer, in the order chosen (ready + inflight <= DRAFT_AHEAD)
    late_sends = []                      # when a send ran QUEUE_LATE_S past its slot (the shallow arm's guard); the writer appends
    inflight = []                        # the jobs the drafters are drafting now (config.DRAFTERS of them at most); guarded by mu
    no_model_until = [0.0]               # no draft before this time: the last one found no model (NO_MODEL_PAUSE_S)
    no_model_times, no_model_alerted = [], [0.0]      # when drafts found no model lately; when we said so (0: not now)
    nm_episode = {}                      # the open no-model episode (since, n, logged, modes, win, last_log, ok_at); guarded by mu

    def nm_close(now_t):
        """The open episode is over: its closing row. The caller holds mu. Returns the "recovered" alert text, if the
        episode was alerted, for the caller to send once it has released mu."""
        ep = dict(nm_episode)
        nm_episode.clear()
        end = ep.get("ok_at") or now_t
        log({"act": "no_model", "phase": "end", "n": ep["n"], "new": ep["n"] - ep["logged"], "modes": ep["win"],
             "modes_total": ep["modes"], "since": dt.datetime.fromtimestamp(ep["since"], dt.timezone.utc).isoformat(),
             "duration_s": round(end - ep["since"]), "alerted": bool(no_model_alerted[0])})
        since, no_model_alerted[0] = no_model_alerted[0], 0.0
        no_model_times[:] = []
        return f"recovered: drafts find a model again (after {(end - since) / 60:.0f} min)" if since else None

    def no_model_ok(answered=True):
        """A model answered a draft (answered=False: just look, the drafter does so every round). The episode ends once
        that has held NO_MODEL_RECOVER_S without a new miss (one lucky answer between misses does not close it and open
        another: that would be a row per flap)."""
        if not nm_episode:
            return
        now_t, say = time.time(), None
        with mu:
            if nm_episode:
                if answered:
                    nm_episode.setdefault("ok_at", now_t)
                if not nm_episode.get("ok_at"):
                    return
                if now_t - nm_episode["ok_at"] >= NO_MODEL_RECOVER_S:
                    say = nm_close(now_t)
        if say:
            alert(say)

    def no_model_hit(mode, wait_s=0.0, pause=None, alerts=None):
        """A draft found no model (or, with pause given, nothing can answer so none was tried). Sets the pause every
        drafter honours (mode, the job kind, is only for the log), counts the attempt into the episode, logs at most
        one row per NO_MODEL_LOG_EVERY_S, and alerts once per episode. wait_s: what the chain knows (llm.no_model_wait)
        stretches the pause up to NO_MODEL_PAUSE_MAX_S; after NO_MODEL_TRIES attempts it stretches to
        NO_MODEL_LONG_PAUSE_S, logged once. Returns the pause in seconds."""
        now_t, say = time.time(), []
        with mu:
            ep = nm_episode
            if ep.get("ok_at") and now_t - ep["ok_at"] >= NO_MODEL_RECOVER_S:
                say.append(nm_close(now_t))                      # a long gap since the last miss: a new episode
            first = not ep
            if first:
                ep.update(since=now_t, n=0, logged=0, modes={}, win={}, last_log=0.0, backoff=False)
            ep.pop("ok_at", None)
            ep["n"] += 1
            ep["modes"][mode] = ep["modes"].get(mode, 0) + 1
            ep["win"][mode] = ep["win"].get(mode, 0) + 1
            stretched = False
            if pause is None:
                pause = max(NO_MODEL_PAUSE_S, min(wait_s, NO_MODEL_PAUSE_MAX_S))
                if ep["n"] >= NO_MODEL_TRIES:
                    pause = max(pause, NO_MODEL_LONG_PAUSE_S)
                    stretched, ep["backoff"] = not ep["backoff"], True      # logged once per episode
            else:
                pause = min(pause, NO_MODEL_PAUSE_MAX_S)
            no_model_until[0] = max(no_model_until[0], now_t + pause)
            no_model_times[:] = [x for x in no_model_times if now_t - x < NO_MODEL_ALERT_S] + [now_t]
            if first or stretched or now_t - ep["last_log"] >= NO_MODEL_LOG_EVERY_S:
                log({"act": "no_model", "phase": "start" if first else "ongoing", "n": ep["n"],
                     "new": ep["n"] - ep["logged"], "modes": ep["win"],
                     "since": dt.datetime.fromtimestamp(ep["since"], dt.timezone.utc).isoformat(),
                     "pause_s": round(pause), "wait_s": round(wait_s), "backoff": ep["backoff"]})
                ep.update(logged=ep["n"], win={}, last_log=now_t)
                print(f"no model answers ({', '.join(f'{m}={c}' for m, c in ep['modes'].items())}); drafting paused "
                      f"{pause:.0f} s, nothing dropped (n={ep['n']})")
            if args.live and not no_model_alerted[0] and (
                    len(no_model_times) >= NO_MODEL_ALERT_N or now_t - ep["since"] >= NO_MODEL_ALERT_AGE_S):
                no_model_alerted[0] = now_t                      # once per episode: no model for minutes
                say.append(f"NO MODEL: {ep['n']} draft attempts in {(now_t - ep['since']) / 60:.0f} min found no model "
                           f"(free ones parked, paid ones over budget or held for amplified posts). Drafting is paused "
                           f"and nothing is dropped; retrying about every {max(1, round(pause / 60))} min. Dashboard 'Drafting' has the numbers.")
        if alerts is not None:                                   # the caller holds mu and sends them after releasing it
            alerts.extend(filter(None, say))
        else:
            for s in filter(None, say):
                alert(s)
        return pause

    beats = {}                         # thread name -> time its loop last went round (status.json, the watchdog)
    workers = []
    # todo/38: the pool orchestrator (pool.py plans, pool_runner.py does). Always planning in the live split loop; it only
    # changes anything when config.POOL_LIVE (SWAN_POOL_LIVE=1), else it logs `pool_shadow` rows. Non-critical worker "pool".
    pool_run = (pool_runner.PoolRunner(accounts, social, mu, log, alert, code, owner, rng=random.Random(),
                                       sent_file=config.DATA / "pool_alerts.json", clock_file=config.DATA / "pool_clock.json")
                if args.live and split else None)
    rate_limited = []                    # times of 429s in the last hour (dashboard)
    write_rl = [None]                    # the write budget as our last write's headers reported it (todo/24)
    last_status = [0.0]

    def portal_sync():
        """todo/40: voices and boosters the portal says are suspended are marked at once (Accounts.sync_portal; a local
        file, no network), instead of at their next 403, which came 40 min to 12 h late."""
        try:
            with mu:
                for username in accounts.sync_portal(log):
                    print(f"portal: @{username} is suspended")
        except OSError as e:                          # a full disk must not stop the writer
            print("portal sync failed:", e)

    hot_last = [None]                    # hot mode: the voice that was writing at the last status write

    def hot_note(t):
        """Hot mode: one log row (act hot_switch) and one alert when the writing voice changes (the old one suspended, the
        next spare took over) or when none is left, and once on the first look. Nothing when hot mode is off."""
        hot = accounts.hot()
        if hot is None:
            return
        with mu:
            stop = hot_track(accounts, hot)
        if (hot["active"] or "none") == hot_last[0]:
            return
        first, hot_last[0] = hot_last[0] is None, hot["active"] or "none"
        log({"act": "hot_switch", "to": hot["active"], "spares": hot["spares"], "lost": hot["lost"],
             "missing": hot["missing"], "first": first})
        if first and hot["active"]:
            return
        left = len(hot["spares"])
        alert(f"HOT: @{hot['active']} now writes ({left} spare left; lost: {', '.join(hot['lost']) or 'none'})" if hot["active"]
              else f"HOT: no hot voice left (lost: {', '.join(hot['lost']) or 'none'}); the bot is idle until SWAN_HOT_VOICES names a live one")
        if stop:
            alert(stop)

    def write_status():
        """data/status.json for the dashboard (todo/09), at most every 30 s. Counts and model names only, no secrets.
        The split loop adds each thread's heartbeat and the queues between them (todo/22)."""
        t = time.time()
        if args.live:
            hot_note(t)                  # every call: a hand-over to a spare is logged at once, not up to 30 s later
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
                **({"hot": accounts.hot()} if config.HOT_VOICES else {}),
                accounts=dict(live=len(accounts.active()), voices=len(accounts.voices()),
                              boosters=len(accounts.boosters()), used=len(recs),
                              suspended=sum(r.get("status") == "suspended" for r in recs)),
                # todo/31: per voice its writes, active hours, hidden posts and what holds it; the two-voice share
                stealth=stealth.metrics(accounts.voices(), accounts.hidden(), state, t,
                                        status=lambda r: accounts.status(r, t)),
                **({"pool": pool_run.status()} if pool_run and pool_run.status() else {}),    # todo/38 (swan_dash pool_view)
                # todo/22: each thread's heartbeat (max_silent_s: the watchdog's limit) and the queues between them
                **(dict(loop="split", threads={name: dict(
                    last_run=dt.datetime.fromtimestamp(b, dt.timezone.utc).isoformat(), age_s=round(t - b),
                    **({"max_silent_s": limits[name]} if name in limits else {})) for name, b in sorted(beats.items())},
                    queue=dict(reply_backs=len(queue), candidates=len(targeter.candidates), drafts_ready=len(ready),
                               drafts_inflight=len(inflight)),
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
        jobs = [d["job"] for d in ready] + list(inflight)
        return [j for j in jobs if mode is None or j["mode"] == mode]

    def save_state():
        if args.live:
            with mu:
                # pending reply-backs survive a restart (their notifications are already marked resolved)
                state["queue"] = [dict(username=j["rec"]["username"], target=j["target"], our_text=j["our_text"],
                                       tries=j.get("tries", 0), depth=j.get("depth"), depth_arm=j.get("depth_arm"))
                                  for j in queue + held() if j["mode"] == "reply_back"]
                save_json(config.STATE_FILE, {**state, "targeter": targeter.dump()})

    def save_room():
        """todo/52: the room's read and counts at the end of a run, so a deploy's restart keeps them (room.load)."""
        if args.live and config.ROOM_ON:
            try:
                room.write()
            except (OSError, ValueError) as e:
                print("room not saved:", e)

    end = time.time() + args.hours * 3600
    next_write = next_notif = 0.0
    queue, stats = [], {"accepted": 0, "rejected": {}, "by_mode": {}}
    by_user = {r["username"]: r for r in accounts.active() if not accounts.parked(r)}
    for q in state.pop("queue", []):
        if q["username"] in by_user and (config.REPLY_BACK or config.REPLY_BACK_AMP):
            queue.append(dict(mode="reply_back", rec=by_user[q["username"]], target=q["target"],
                              our_text=q["our_text"], tries=q.get("tries", 0), depth=q.get("depth"),
                              depth_arm=q.get("depth_arm")))
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
        ids = {r.get("account_id") for r in accounts.records if r.get("account_id")}
        try:        # todo/46: voices whose notifications poll_reply_backs does not read (suspended, parked, on standby): late replies
            targeter.dead_ids = ids - {r.get("account_id") for r in accounts.voices() if not accounts.parked(r)}
        except Exception:
            pass
        return ids

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
        # 23 Oct, several drafters: a citizen one drafter is drafting for is not given to another meanwhile (two voices
        # answering at once would not see each other's text). Their reply-backs, second voices and candidates wait.
        busy = {str(j["target"].get("author_id")) for j in inflight if j.get("target")}
        cit_contacted = {a: set(v) for a, v in contacted.items()}
        for a in busy:
            cit_contacted.setdefault(a, set()).update(f"<drafting {i}>" for i in range(config.SESSION_VOICES))
        pending = [j["mode"] for j in held()]               # chosen but not sent yet: counted as written (todo/22)
        job = None
        # the first reply-back whose voice may write: not within reply_back_gap() of its last write (don't double-post
        # from one account), and awake and under its caps (todo/31: it answers when it wakes; the rest go meanwhile)
        for j in queue:
            if j["rec"].get("last_write", 0) + reply_back_gap() > t:
                continue
            if j["rec"]["persona"] in accounts.reserved or str(j["target"].get("author_id")) in busy:
                continue                  # its voice or citizen is being drafted for by another drafter: next round
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
            rec = accounts.eligible(exclude=accounts.young(t))          # todo/40: not a voice in its first hours
            if rec:
                job = dict(mode="post", rec=rec, frame=content.pick_frame(content.PERSONA_BY_KEY[rec["persona"]]))
        # batched drafting (--batch, not run live) keeps its replies after the amplifier, further down
        job = pick_job(job, (lambda: None) if desk else
                       (lambda: citizen_reply(targeter, accounts, ids, state["replied_posts"], cit_contacted, engaged,
                                              state)), amp)
        drafted = None
        if job is None and amp and amp.priority_window():          # priority lane: the fresh thread gets the slots
            return None, None, WAIT_S["priority"]
        gone = lambda j: ((j.get("target") or {}).get("post_id") in state["replied_posts"]
                          or (j["mode"] == "reply"
                              and len(contacted.get(str(j["target"]["author_id"]), ())) >= config.SESSION_VOICES))
        second = config.SECOND_VOICE and not stealth.one_voice_on()     # todo/31: one voice per citizen (todo/38: auto from 24 writers)
        if job is None and desk and second:
            drafted = desk.take("second_voice", t, gone)
        if job is None and drafted is None and second:
            state["second_voice"] = [s for s in state["second_voice"] if t - s["due"] < 3600]   # stale after 1 h
            due = [s for s in state["second_voice"] if s["due"] <= t]
            picked = []
            for sv in due:
                if str(sv["author"]) in busy:
                    continue                                     # a draft for them is under way: kept for the next round
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
                if target_class(target.get("body") or "") == "off_topic":
                    continue                                     # no vote pitch into a thread about something else
                job = dict(mode="second_voice", rec=rec, target=target, frame=sv["frame"],
                           wants=sv.get("wants"), context=sv.get("context"), news=sv.get("news", True),
                           sv_delay=sv.get("sv_delay"),
                           defer=lambda sv=sv: sv in state["second_voice"] or state["second_voice"].append(sv))   # no model: kept
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
                    rec = accounts.assignable(exclude=desk.busy("post", picked) | accounts.young(t))    # todo/40
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
            rec = accounts.eligible(exclude=accounts.young(t))                       # todo/40
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
        job.setdefault("t_pick", time.time())                # reply-time stages (dashboard): chosen, drafted, sent
        persona = persona_of(rec)
        text = backend = user = repair = None
        if mode == "repost":
            text, backend = "", "none"
        elif drafted:
            text, backend = drafted["text"], drafted["backend"]
            job["drafted_ahead"] = True
        else:
            if mode in config.MENTION_MODES and target and "mention" not in job:
                job["mention"] = mention.plan(job, targeter, state.get("mentioned"))    # todo/46; a public read, outside mu
            with mu:                                 # drafts waiting to be sent count as sent (todo/22)
                recent_texts = state["recent_texts"] + [d["text"] for d in ready if d["text"]]
                recent_shapes = state["recent_shapes"] + [d["job"]["meta"]["shape"] for d in ready
                                                          if (d["job"].get("meta") or {}).get("shape")]
                if mode in quality.PERSONAL_KINDS and target and config.writes_to_citizen(target.get("author_id")):
                    job["phrase_texts"] = citizen_texts(state.get("recent_sent", []), ready)     # todo/27
                if mode in STYLE_MODES:                                                  # todo/50
                    job["memory"] = style_memory(state, job)
                persona, system, user = build_prompt(job, targeter, recent_shapes, pulse_now, recent_texts=recent_texts)

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
                if backend is not None:
                    no_model_ok()                     # a model answered (even if the gate then refused the draft)
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
            if backend is None:
                # no model could answer: whatever the mode, the job goes back (lose -> defer) and the episode counts
                # it. The pause is set first, so no drafter can pick the same job meanwhile (mu is held below).
                alerts = []
                with mu:                              # hit and deferral in one hold: no drafter sees the job in between
                    no_model_hit(mode, model_wait(gen), alerts=alerts)
                    lose(targeter, queue, job, "no_model")
                for s in alerts:
                    alert(s)
                return None
            with mu:
                lose(targeter, queue, job, f"gate:{(job.get('meta') or {}).get('last_reject') or 'unknown'}")
            return None
        job["t_drafted"] = time.time()
        return dict(job=job, drafted=drafted, text=text, backend=backend, repair=repair, persona=persona)

    def send(d):
        """Send one checked draft and record it: the send-time checks, the write, then the state and the log."""
        nonlocal next_write
        job, drafted, text, backend, repair, persona = (d[k] for k in ("job", "drafted", "text", "backend", "repair",
                                                                       "persona"))
        rec, mode, target = job["rec"], job["mode"], job.get("target")
        with mu:
            # suspended or benched (StuckWrites) while the draft waited (hot mode switches voice): no 403
            if rec.get("status", "active") != "active" or rec["username"] in accounts.benched:
                log({"act": "skip", "why": "voice_gone_at_send", "mode": mode, "persona": persona["key"],
                     "target_post": target and target["post_id"], "draft_id": job["draft_id"]})
                if job.get("cand"):
                    targeter.requeue(job["cand"], "held")
                return
            if accounts.parked(rec):                  # hit the hidden-post limit while the draft waited (23 Oct audit:
                log({"act": "skip", "why": "parked_at_send", "mode": mode, "persona": persona["key"],     # 6 of 7 voices
                     "target_post": target and target["post_id"], "draft_id": job["draft_id"]})            # kept writing)
                if job.get("cand"):
                    targeter.requeue(job["cand"], "held")         # another voice may take the citizen
                return
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
            text, hand = humanize.apply(text, persona.get("hand", persona["key"]), mode,
                                        target_text=(target or {}).get("body") if job.get("fixes") else None,
                                        mirror=bool(job.get("fixes")))                  # todo/50: their register
            if mention.used(clean, job.get("mention")) and f"@{job['mention']['username']}" not in text:
                text, hand = clean, []             # the hand must not touch a handle: send the clean text

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
                try:
                    r = write(acc)
                except ctn.APIError as e:
                    if e.status != 401:
                        raise
                    acc = accounts.relogin(rec)
                    r = write(acc)
            except ctn.APIError as e:
                e.write_by = rec["username"]      # handle(): the write (or its re-login) failed, not a read (StuckWrites)
                raise
            stuck.ok()
            post_id = r["post_id"]
            write_rl[0] = acc.rate_limit             # the team-wide write budget, as this answer reported it
        with mu:
            if target and mode in engage.FOLLOW_MODES + engage.LIKE_MODES:      # todo/33: the citizen's cell
                engage.push(state, engage.plan(job, rec, target["author_id"], target["post_id"]))
            if mention.used(text, job.get("mention")):     # todo/46: this citizen is named for MENTION_RECONTACT_S
                now_m = time.time()
                state["mentioned"] = {k: v for k, v in (state.get("mentioned") or {}).items()
                                      if now_m - v < config.MENTION_RECONTACT_S}
                state["mentioned"][str(job["mention"]["author_id"])] = now_m
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
            if target and mode == "reply" and args.live:  # todo/52: the light read of a post we answered, for the room
                room.observe(target["post_id"], target.get("body") or "", stance=(job.get("meta") or {}).get("read_stance"))
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
                arms = list(stealth.second_voice_arms())              # todo/20 step 7 (todo/38: no 'fast' arm in a big pool)
                job["sv_delay"] = (experiment.per_voice_day("sv_delay", arms, rec["username"])    # todo/40: per voice-day
                                   if config.SV_DELAY_PER_VOICE_DAY else experiment.alternate("sv_delay", arms))
                state["second_voice"].append(dict(due=time.time() + random.uniform(*config.SECOND_VOICE_ARMS[job["sv_delay"]]),
                                                  sv_delay=job["sv_delay"],
                                                  post_id=target["post_id"], author=target["author_id"],
                                                  frame=second_frame(job["frame"]),
                                                  first_persona=persona["key"], wants=job.get("wants"),
                                                  context=job.get("context"), news=context_is_news(job)))
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
                if mode in STYLE_MODES:               # todo/50: the voice's own texts and items, the citizen's history
                    memory.record(state, rec["username"],
                                  target["author_id"] if target and config.writes_to_citizen(target["author_id"]) else None,
                                  clean, items=(job.get("meta") or {}).get("items"))
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
             **{k: job.get(k) for k in ("priority", "arm", "engaged", "lead")},       # todo/21; lead: the model tried first
             "eng_cell": engage.cell(target["author_id"]) if target and mode in stealth.CITIZEN_MODES else None,
             "length": len(clean or ""), **{k: meta.get(k) for k in ("llm_calls", "repairs", "fixes")},  # G9
             # todo/20: the reply style arm and the light read; todo/21's arm and priority, next to target_class
             "arm": job.get("arm"), "priority": job.get("priority"), "group": job.get("group"),
             "net": job.get("net"),                       # todo/23: the arm it counts against (engaged + off_topic)
             "sv_delay": job.get("sv_delay"),
             "mention": (job.get("mention") or {}).get("username") if mention.used(text, job.get("mention")) else None,
             "mention_target": (job.get("mention") or {}).get("author_id"),     # todo/46: planned; `mention` says it was written
             **{k: job.get(k) for k in ("queue_arm", "ready_n", "ready_s")},    # 26 Oct: the send-queue arm, its depth, the draft's wait
             **{k: job.get(k) for k in ("ev", "arm_pick")},                     # todo/49: expected points at the pick, the pick arm
             "touch_gap_h": job.get("touch_gap_h"),                             # todo/46: hours since we last wrote to this citizen
             # todo/48: a citizen above id 2343 by the cached score (the extra arm's candidates, and reply-backs to them)
             "npc_score": job.get("npc_score", config.npc_target(target.get("author_id")) if target else None),
             "depth": job.get("depth"), "depth_arm": job.get("depth_arm"),    # reply-backs: posts above the citizen's reply
             **stage_times(job, target),
             "own_like": job.get("own_like"),
             "frame_in": job.get("frame_in"),
             **{k: meta.get(k) for k in ("read_ok", "read_stance", "read_doubt", "read_frame", "agree_by", "redrafted")},
             "catchphrase": content.catchphrase_in(text), "identity": job.get("identity"),
             "messenger_match": bool(job.get("identity")) and persona["key"] in messengers(job.get("identity")),
             "thread": threading.current_thread().name,                                   # todo/22: the writer
             "eng_cell": engage.cell(target["author_id"]) if target and mode in stealth.CITIZEN_MODES else None,
             **({k: drafted[k] for k in ("batch_id", "batch_pos", "batch_size")} if drafted else {})})
        where = ""
        if target:
            ctx = f" [under: {job['context'][:60]!r}]" if job.get("context") else ""
            where = f"\n    -> #{target['post_id']} (author {target['author_id']}){ctx}: {(target.get('body') or '')[:200]!r}"
        via = f"|{drafted['batch_id']} #{drafted['batch_pos'] + 1}/{drafted['batch_size']}" if drafted else ""
        tags = "|".join(str(meta[k]) for k in ("voice", "shape") if meta.get(k))
        print(f"[{mode}|{job['frame']}|{tags}|{backend}{via}] {persona['name']}{where}\n    {text}\n")

    net_fails = [0]                      # transient network errors in a row on the writer (reset by a send)
    sus_403 = []                         # times of the 403 "suspended" answers in the last HOT_HANDOVER_WINDOW_S (hot mode)
    stuck = StuckWrites()                # failed writes since the last one that went through (send resets it)

    def stuck_write(rec, e):
        """A write by rec failed with a 401/403 that is not a suspension or the feed lock (StuckWrites): log and alert once
        the voice is stuck, and in hot mode bench it so the next spare writes. Returns the writer's wait (s)."""
        msg = (e.message or "")[:160]
        with mu:
            what = stuck.fail(rec["username"], bool(config.HOT_VOICES))
            if what == "bench":
                accounts.benched.add(rec["username"])
            told = stuck.told
        if what:
            log({"act": "write_stuck", "username": rec["username"], "status": e.status, "message": msg, "in_row": stuck.n,
                 "benched": what == "bench"})
        if what == "bench":
            alert(f"WRITES STUCK: @{rec['username']}'s last {STUCK_N} writes failed ({e.status} {msg}), not as a suspension. "
                  f"Benched it for this run (not marked suspended; a restart brings it back): the next spare writes now.")
        elif what == "alert":
            why = (f" after @{' and @'.join(stuck.benched)} was benched, so it is not the voice (the team's clearance? the "
                   f"platform?)" if stuck.benched else "")
            alert(f"WRITES STUCK: {stuck.n} writes in a row failed ({e.status} {msg}){why}. Nothing else is switched; the "
                  f"bot tries again every {STUCK_WAIT_S} s. Logs: journalctl -u swan-bot -n 50")
        return 0 if what == "bench" else STUCK_WAIT_S if told else 10      # benched: the spare writes at once

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
                    accounts.mark_suspended(job["rec"])                  # todo/38: the pool's loss rate reads suspended_at
                log({"act": "suspended", "username": job["rec"]["username"]})
                if hot_handover_now(sus_403, time.time()):
                    return
            elif e.status == 403 and "locked" in msg:
                wait(300)
            elif e.status in (401, 403) and job and getattr(e, "write_by", None):
                wait(stuck_write(job["rec"], e))
                return
            wait(10)
        elif isinstance(e, openai.APIError):
            print("LLM error", type(e).__name__, str(e)[:120])
            wait(20)
        elif isinstance(e, content.AllPaused):        # the fact desk paused every frame: wait for a review
            print(e)
            wait(300)
        elif isinstance(e, TRANSIENT_NET):            # one request dropped (23 Oct); outages (NET_MAX_IN_ROW) still raise
            net_fails[0] += 1                         # a write's outcome is unknown, so the draft is not sent again
            log({"act": "net_error", "why": type(e).__name__, "mode": (job or {}).get("mode"), "in_row": net_fails[0],
                 "target_post": ((job or {}).get("target") or {}).get("post_id")})
            if net_fails[0] >= NET_MAX_IN_ROW:
                raise e
            print(f"network error ({net_fails[0]}/{NET_MAX_IN_ROW}): {type(e).__name__}: {e}"[:300])
            wait(NET_RETRY_S)
        else:
            raise e

    LOOP_ERRORS = (ctn.APIError, openai.APIError, content.AllPaused)
    WRITE_ERRORS = LOOP_ERRORS + TRANSIENT_NET       # the loops that send: a dropped connection costs one round

    # ---- the serial loop (config.SPLIT_LOOP off): read, draft and write in turn, as before todo/22 ----
    def serial_loop():
        while time.time() < end and not (args.samples and stats["accepted"] >= args.samples):
            job = None
            write_status()
            portal_sync()
            try:
                register()
                if not accounts.voices():
                    pause(WAIT_S["no_voice"])
                    continue
                ids = our_ids()
                if targeter.refresh():
                    save_state()
                own_likes(state, accounts, args.live)
                engage_actions(state, accounts, args.live)
                pulse_now = pulse.update(state, targeter, ids, gen, log)
                if amp:
                    amp.tick()
                poll_reply_backs()
                no_model_ok(answered=False)

                wait = next_write - time.time()
                if wait > 0:
                    pause(min(wait, 30))
                    continue
                if time.time() < no_model_until[0]:
                    pause(min(no_model_until[0] - time.time(), 30))
                    continue
                wait_m = model_wait(gen)
                if wait_m > 0 and not args.allow_qwen:       # nothing can answer (parked, or the budget holds the paid ones)
                    no_model_hit("any", wait_m, pause=wait_m + 1)
                    continue
                job, drafted, wait = choose(time.time(), ids)
                if job is None:
                    pause(wait)
                    continue
                d = draft(job, drafted, pulse_now)
                if d:
                    send(d)
                    net_fails[0] = 0
            except WRITE_ERRORS as e:
                handle(e, job, pause)
            except KeyboardInterrupt:
                if job and job.get("mode") == "reply_back" and job not in queue:
                    queue.insert(0, job)                  # stopped mid-draft: keep the citizen's reply for next run
                break
        save_state()
        save_room()

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
        """Choose the next job and draft it while the writer waits for its slot. config.DRAFTERS of these run at once,
        each with its own job: choose() and the reservation of the job's voice happen together under mu, so two
        drafters never hold the same voice or citizen, and drafts chosen but not sent (ready + inflight) stay at most
        DRAFT_AHEAD. todo/58: in shallow blocks it also waits until the writer's next slot is JIT_LEAD_S away (jit_hold)."""
        def full():
            with mu:
                arm = queue_arm(late_sends=late_sends)
                return len(ready) + len(inflight) >= draft_ahead(arm) or jit_hold(next_write, time.time(), arm)
        no_model_ok(answered=False)          # a spell of no model ends once a model has answered for a while
        if full():
            stop.wait(IDLE_S)
            return
        if not accounts.voices():
            stop.wait(WAIT_S["no_voice"])
            return
        if time.time() < no_model_until[0]:
            stop.wait(max(0.1, no_model_until[0] - time.time()))
            return
        job = d = None
        try:
            ids = our_ids()
            with mu:                                     # the pulse thread refreshes it (pulse_step); drafters only read
                pulse_now = pulse.current(state)
            wait_m = model_wait(gen)
            if wait_m > 0 and not args.allow_qwen:           # nothing can answer (parked, or the budget holds the paid ones)
                no_model_hit("any", wait_m, pause=wait_m + 1)    # one episode row; the pause holds every drafter
                return
            woken.clear()
            with mu:
                arm = queue_arm(late_sends=late_sends)
                if len(ready) + len(inflight) >= draft_ahead(arm) or jit_hold(next_write, time.time(), arm):
                    return                                   # the others filled it while this one waited (or the slot moved)
                job, drafted, wait = choose(time.time(), ids)
                if job:
                    if not config.HOT_VOICES:                           # hot mode: one voice has several drafts at once
                        accounts.reserved.add(job["rec"]["persona"])    # no second draft for this voice meanwhile
                    inflight.append(job)
            if job is None:
                woken.wait(wait)                                      # or until the reader finds something
                return
            d = draft(job, drafted, pulse_now)
        except LOOP_ERRORS as e:
            handle(e, job, stop.wait)
        finally:
            with mu:
                if job:
                    inflight[:] = [j for j in inflight if j is not job]
                if d and clashes_with_ready(d["text"], job["mode"], ready):
                    # a draft that finished while this one was under way: the gate could not compare with it
                    log({"act": "reject", "why": "clash_concurrent", "mode": job["mode"],
                         "draft_id": job.get("draft_id"), "target_post": (job.get("target") or {}).get("post_id")})
                    lose(targeter, queue, job, "clash_concurrent")
                    d = None
                if d:
                    d["ready_at"] = time.time()
                    ready.append(d)
                elif job:
                    accounts.reserved.discard(job["rec"]["persona"])

    def pulse_step():
        """The pulse thread (23 Oct): refreshes state["pulse"] on pulse.update's own cadence (PULSE_EVERY_S, a third of
        that after a failure), so no drafter spends time on its LLM call. The call runs on a copy outside mu; the two
        state keys are written back inside it. A failed refresh keeps the last pulse (drafts go on with it until
        PULSE_MAX_AGE_S) and is retried after a third of PULSE_EVERY_S, logged once per failure."""
        if not config.PULSE_ON:
            stop.wait(PULSE_POLL_S)
            return
        with mu:
            kept = {k: state[k] for k in ("pulse", "pulse_next") if k in state}
        due = kept.get("pulse_next", 0)
        if time.time() < due:
            stop.wait(min(PULSE_POLL_S, max(1.0, due - time.time())))
            return
        if stop.is_set():
            return
        try:
            pulse.update(kept, targeter, our_ids(), gen, log)
        except Exception as e:                  # noqa: BLE001 - a duty the bot can do without: never kill the thread
            kept["pulse_next"] = time.time() + config.PULSE_EVERY_S / 3
            log({"act": "pulse_error", "why": type(e).__name__, "detail": str(e)[:200]})
            print(f"pulse refresh failed ({type(e).__name__}): {e}"[:300])
            if isinstance(e, LOOP_ERRORS):
                handle(e, None, stop.wait)
        with mu:
            state.update(kept)

    room_next = [time.time() + 60]       # todo/52: the first room read a minute after the start

    def room_step():
        """The room thread (todo/52, non-critical): data/room.json and the counts behind it every ROOM_EVERY_S. Read-only,
        no network: a failed write is logged and tried again next time."""
        wait = room_next[0] - time.time()
        if wait > 0 or not config.ROOM_ON:
            stop.wait(min(PULSE_POLL_S, max(1.0, wait)))
            return
        room_next[0] = time.time() + config.ROOM_EVERY_S
        try:
            room.write()
        except (OSError, ValueError) as e:
            log({"act": "room_error", "why": type(e).__name__, "detail": str(e)[:200]})

    def pool_step():
        """The pool thread (todo/38, non-critical): one tick of the pool orchestrator every POOL_TICK_S (30-60 s). It never
        holds mu across a network call (pool_runner), a failing tick is logged and the 5th in a row ends the thread, which
        the watchdog reports once; the bot keeps writing with the pool it has."""
        pool_run.step()
        stop.wait(random.uniform(*config.POOL_TICK_S))

    def check_workers():
        """The watchdog (todo/22): a thread that died or went silent stops the bot. It logs, alerts like BOT CRASHED,
        saves the state and exits 1, so systemd restarts it. Never runs on without its reader or drafter. The pulse
        thread (critical=False) only logs and alerts, once per spell: drafts use the last pulse without it."""
        if stop.is_set():
            return
        for w in workers:
            why = w.problem()
            if not w.critical:
                if why and not w.reported:
                    w.reported = True
                    log({"act": "thread_died", "thread": w.name, "why": why, "fatal": False})
                    print(f"watchdog: {w.name} {why} (not fatal)")
                    if args.live:
                        alert(f"BOT THREAD FAILED (not fatal): {w.name} ({why}); "
                              + ("no accounts are added or activated until a restart; the bot keeps writing. "
                                 if w.name == "pool" else
                                 "data/room.json stops updating and the room lifts nothing; the bot keeps writing. "
                                 if w.name == "room" else "drafts use the last pulse. ")
                              + "Restart when convenient. Logs: journalctl -u swan-bot -n 50")
                elif not why:
                    w.reported = False
                continue
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
        save_room()

    def write_loop():
        while time.time() < end and not stop.is_set() and not (args.samples and stats["accepted"] >= args.samples):
            beats["writer"] = time.time()
            check_workers()
            write_status()
            portal_sync()
            job = None
            try:
                register()
                if save_due.is_set():
                    save_due.clear()
                    save_state()
                with mu:
                    own_likes(state, accounts, args.live)
                    engage_actions(state, accounts, args.live)
                    if amp:
                        amp.tick()
                wait = next_write - time.time()
                if wait > 0:
                    pause(min(wait, 30))
                    continue
                with mu:                     # the draft to send: the first whose voice may write now, or the freshest (arm_queue)
                    t = time.time()
                    arm = queue_arm(t, late_sends)
                    d = pick_ready(ready, lambda r: voice_wait(r["job"], accounts, args.live, t) <= 0, arm, t)
                    if d:
                        ready.remove(d)
                        d["job"].update(queue_arm=arm, ready_n=len(ready) + 1, ready_s=round(t - d.get("ready_at", t), 1))
                        if -wait > config.QUEUE_LATE_S:      # the slot opened this long ago and nothing was ready
                            late_sends.append(t)
                            del late_sends[:-20]
                if d is None:
                    engage_actions(state, accounts, args.live)
                    pause(IDLE_S)
                    continue
                job = d["job"]
                send(d)
                net_fails[0] = 0
            except WRITE_ERRORS as e:
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
            workers += [Worker("reader", reader_step, stop, beats, config.READER_SILENT_S)]
            workers += [Worker(f"drafter-{i}", drafter_step, stop, beats, config.DRAFTER_SILENT_S)
                        for i in range(1, max(1, int(config.DRAFTERS)) + 1)]
            workers += [Worker("pulse", pulse_step, stop, beats, config.PULSE_SILENT_S, critical=False)]
            if args.live:                                # todo/52: a dry run reads a fixture; its room is not the room
                workers += [Worker("room", room_step, stop, beats, config.ROOM_SILENT_S, critical=False)]
            if pool_run:
                workers += [Worker("pool", pool_step, stop, beats, config.POOL_SILENT_S, critical=False)]
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
