"""Pool orchestrator, executor (todo/38). Runs as the non-critical "pool" worker of swan-bot (bot.py); the plan itself is
swan_bot/pool.py (pure). This module does the I/O around it, under these rules:

* NEVER holds the bot's `mu` across a network call. A registration is: take mu, check the caps and write the intent record
  (username, password, the whole variant, status "pending") with Accounts.save, release; call the API; take mu, write the
  result. A crash between any two steps leaves a "pending" record, and reconcile() finishes it by login (found: it is the
  account, finished; 401/404 after 2 min: it never existed, marked "failed"). It never registers the same username twice.
* DRY unless config.POOL_LIVE (and the bot is live, and no POOL_OFF file): then it plans on a private copy of the records
  (secrets stripped) and logs `pool_shadow` rows of what it WOULD do, applying them to the copy so the plan evolves as it
  would (warm-ups elapse, warmed accounts activate). Nothing real is registered, converted, saved or called.
* The only registrar while live: Accounts.maybe_register and Amplifier.maybe_register_booster stand down (bot.py, amplify.py).
* Every action logs a row with by="pool", reason, owner (config.operator()): pool_register | pool_convert | pool_activate |
  pool_shadow | pool_error, in logs/swan_actions.jsonl. No password, token or team code is ever logged.
* Fail static: a tick that raises is logged; five in a row re-raise so the watchdog alerts once ("not fatal") and the bot keeps
  writing with the pool it has.
"""
import http.client
import json
import random
import re
import secrets
import socket
import ssl
import time
import urllib.error

import capturethenarrative as ctn

from . import budget, config, content, pool, stealth, variants

VARIANT_TRIES = 3                 # make_variant calls per account when the best one still fails distinct()
RECONCILE_MIN_AGE_S = 120         # a pending record younger than this is never judged "failed" (a late answer may be on its way)
RECONCILE_RETRY_S = 60
ERRORS_IN_ROW = 5
NET = (urllib.error.URLError, ssl.SSLError, socket.timeout, ConnectionError, http.client.HTTPException, OSError)
SECRET_KEYS = ("password", "token")


def strip(rec):
    """A copy of an account record without its secrets (what the shadow keeps and what variants.make_variant reads)."""
    return {k: v for k, v in rec.items() if k not in SECRET_KEYS}


def swarm_counts():
    """(active, total, usernames) of the swarm's own file (read only: swan-swarm owns it)."""
    try:
        recs = json.loads(config.SWARM_ACCOUNTS_FILE.read_text())
    except (OSError, ValueError):
        return 0, 0, set()
    recs = [r for r in recs if isinstance(r, dict)]
    return (sum(1 for r in recs if r.get("status", "active") == "active"), len(recs),
            {r.get("username", "").lower() for r in recs})


def default_cards():
    """Card keys a new voice may take: the LIVE cards (content.PERSONAS). The staged ones are not promoted."""
    return [p["key"] for p in content.PERSONAS]


class PoolRunner:
    def __init__(self, accounts, social, mu, log, alert, code, owner, *, clock=time.time, rng=None, cards=None,
                 swarm=None, params=None, live=None, off=None, say=print, sent_file=None, clock_file=None):
        self.accounts, self.social, self.mu, self.log, self.alert = accounts, social, mu, log, alert
        self._code, self.owner = code, owner                      # the team code is only ever passed to social.register
        self.clock = clock
        self.rng = rng or random.Random()
        self.cards = cards or default_cards
        self.swarm = swarm or swarm_counts
        self.p = params or pool.Params.from_config(config)
        self.live_fn = live or (lambda: bool(config.POOL_LIVE))
        self.off_fn = off or config.POOL_OFF_FILE.exists
        self.say = say
        self.sent_file = sent_file                                # alerts already sent, kept across restarts (None: not kept)
        self.st = pool.PoolState(z=pool.draw_z(self.rng))
        self.clock_file = clock_file                              # want_since and z, kept across restarts (None: not kept)
        self._clock_saved = None
        self._load_clock()
        self.shadow, self.shadow_new = {}, []                     # the shadow's private copy: {username: record}, [records]
        self.suspended_ts = {}                                    # {username: epoch} for suspensions with no suspended_at
        self._seeded = False
        self._announced = False
        self._retry = {}                                          # {username: epoch} next reconcile attempt
        self.errors = 0
        self._status = None
        self._error_logged = 0.0

    # ---- switches --------------------------------------------------------------------------------------------------
    def is_live(self):
        """May this tick change anything real? The bot is live, POOL_LIVE is on, and there is no POOL_OFF file."""
        return bool(self.accounts.live and self.live_fn() and not self.off_fn())

    def _row(self, act, **kw):
        self.log({"act": act, "by": "pool", "owner": self.owner, **{k: v for k, v in kw.items() if v is not None}})

    # ---- the tick -----------------------------------------------------------------------------------------------------
    def step(self):
        """The worker's body: one tick, riding out an error (fail static). The 5th in a row is raised for the watchdog."""
        try:
            self.tick()
            self.errors = 0
        except Exception as e:                                    # noqa: BLE001 - a duty the bot can do without
            self.errors += 1
            now = self.clock()
            if now - self._error_logged > 300 or self.errors >= ERRORS_IN_ROW:
                self._error_logged = now
                self._row("pool_error", why=type(e).__name__, detail=str(e)[:200], in_row=self.errors)
            self.say(f"pool tick failed ({type(e).__name__}): {e}"[:300])
            if self.errors >= ERRORS_IN_ROW:
                raise

    def tick(self, now=None):
        now = self.clock() if now is None else now
        self._seed()
        live_mode = self.is_live()
        if not self._announced:
            self._announced = True
            self.say(f"pool orchestrator: {'LIVE (registers, converts, activates)' if live_mode else 'shadow / dry run (logs pool_shadow rows, changes nothing)'}; "
                     f"writers target {self.p.writers}, pipeline {self.p.pipeline}, cards {len(self.cards())}")
        off = bool(self.accounts.live and self.live_fn() and self.off_fn())
        if self.accounts.live and self.live_fn():
            self.reconcile(now)
        alerts = []
        plan = None
        with self.mu:
            view = self._view(live_mode)
            self._note_suspensions(view, now)
            snap = self._snapshot(view, now)
            self._track_want(snap, now)
            if not off:
                plan = pool.plan_step(snap, now, self.rng, self.p)
            alerts += self._alert_flags(snap, now, plan)
        for text in self._due(alerts):
            self.alert(text if live_mode else text.replace("POOL", "POOL (dry run)", 1))
        if plan:
            if live_mode:
                self._do_live(plan, snap, now)
            else:
                self._do_shadow(plan, snap, now)
        with self.mu:
            view = self._view(live_mode)
            snap = self._snapshot(view, now)
            self._status = pool.status_dict(snap, self.st, self.p, now, dry_run=not live_mode, off=off)
        self._save_clock()
        return plan

    # ---- the paced delay's clock, across restarts ---------------------------------------------------------------------
    def _load_clock(self):
        """want_since and z from clock_file. Kept in memory only, every restart (each deploy: 11 on 25 Oct) started the
        healthy 5 h wait again from the restart and drew a new z, so the delay only ever grew (25 Oct: next add 872 min away,
        nothing registered since 24 Oct 09:33). A missing or bad file, or a want in the future: a fresh start, as before."""
        if not self.clock_file:
            return
        try:
            doc = json.loads(self.clock_file.read_text())
            z, since = float(doc["z"]), doc.get("want_since")
        except (OSError, ValueError, KeyError, TypeError):
            return
        if pool.Z_CLIP[0] <= z <= pool.Z_CLIP[1]:
            self.st.z = z
        if isinstance(since, (int, float)) and not isinstance(since, bool) and 0 < since <= self.clock():
            self.st.want_since = float(since)
        self._clock_saved = (self.st.want_since, self.st.z)

    def _save_clock(self):
        if not self.clock_file or (self.st.want_since, self.st.z) == self._clock_saved:
            return
        try:
            self.clock_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.clock_file.with_suffix(".tmp")
            tmp.write_text(json.dumps({"want_since": self.st.want_since, "z": self.st.z}))
            tmp.replace(self.clock_file)
            self._clock_saved = (self.st.want_since, self.st.z)
        except OSError as e:
            self.say("pool clock: not saved:", e)

    def status(self):
        """data/status.json["pool"] as of the last tick (None before the first)."""
        return self._status

    # ---- views and snapshots ----------------------------------------------------------------------------------------
    def _view(self, live_mode):
        """The records the plan reads: the real ones when live, else the real ones as secret-free copies with the shadow's
        changes laid over them. The caller holds mu."""
        real = self.accounts.records
        if live_mode:
            return real
        out = []
        for r in real:
            u, s = r.get("username"), None
            s = self.shadow.get(u)
            if s is not None and pool.status_of(r) != "active":
                self.shadow.pop(u, None)                          # the platform took it: the shadow's change is moot
                s = None
            out.append(s if s is not None else strip(r))
        return out + self.shadow_new

    def _snapshot(self, view, now):
        alive, used, _ = self.swarm()
        reporter = config.blue_reporter(self.accounts.records) if self.accounts.live else None
        return pool.snapshot(view, now, self.p, cards=self.cards(), swarm_alive=alive, swarm_used=used,
                             suspended_ts=self.suspended_ts, reporter=(reporter or {}).get("username"), st=self.st)

    def _seed(self):
        """Once: when the already-suspended accounts were lost, from the actions log (`suspended` rows), so loss_per_day
        and the runway are right from the first tick. Accounts the log does not name count as old (time 0)."""
        if self._seeded:
            return
        self._seeded = True
        found = {}
        try:
            from . import jsonl
            for row in jsonl.Reader(config.ACTIONS_LOG, contains='"suspended"'):
                if row.get("act") == "suspended" and row.get("username") and row.get("ts"):
                    t = pool.parse_ts(row["ts"])
                    if t is not None:
                        found[row["username"]] = t
        except OSError:
            pass
        with self.mu:
            for r in self.accounts.records:
                if pool.status_of(r) == "suspended" and r.get("username"):
                    self.suspended_ts[r["username"]] = found.get(r["username"], 0.0)

    def _note_suspensions(self, view, now):
        for r in view:
            u = r.get("username")
            if pool.status_of(r) == "suspended" and u and u not in self.suspended_ts and not r.get("suspended_at"):
                self.suspended_ts[u] = now

    def _track_want(self, snap, now):
        if pool.add_wanted(snap):
            if self.st.want_since is None:
                self.st.want_since = now
                snap["want_since"] = now
        else:
            self.st.want_since = None
            snap["want_since"] = None

    def _due(self, texts):
        """The alerts not sent within config.BUDGET_ALERT_GAP_S. The flags in _alert_flags live in memory, so every restart
        (each deploy) re-armed them and the team channel got the same runway line again; sent_file survives a restart."""
        if not texts or not self.sent_file:
            return texts
        try:
            sent = json.loads(self.sent_file.read_text())
        except (OSError, ValueError):
            sent = {}
        due, sent = budget.due_alerts(texts, sent if isinstance(sent, dict) else {}, self.clock(), config.BUDGET_ALERT_GAP_S)
        try:
            self.sent_file.parent.mkdir(parents=True, exist_ok=True)
            self.sent_file.write_text(json.dumps(sent))
        except OSError as e:
            self.say("pool alerts: sent state not saved:", e)
        return due

    def _alert_flags(self, snap, now, plan):
        """Alert texts due now, each once (re-armed when the condition clears). The caller holds mu; it sends them after."""
        out, flags = [], self.st.flags
        why = pool.waiting_reason(snap, self.p, now)
        if why == "no_free_card":
            if "no_free_card" not in flags:
                flags.add("no_free_card")
                self._row("pool_error", why="no_free_card", state=snap["state"], supply=snap["supply"],
                          target=snap["target"], free_cards=0, reserved=snap["reserved_cards"])
                out.append(f"POOL: no free persona card (writers {snap['voices']}/{snap['target']}, state {snap['state']}); "
                           f"every card is held by an active voice or reserved. Waiting: promote more cards (todo/36) or "
                           f"expect a suspension to free one.")
        elif snap["free_cards"]:
            flags.discard("no_free_card")                          # re-armed only when a card really is free again
        if snap["terminal"] and "total_cap" not in flags:
            flags.add("total_cap")
            out.append(f"POOL: the platform refused a registration for the TOTAL account allowance ({snap['terminal']}). "
                       f"The pool will not register again; conversions of boosters continue.")
        if snap["runway_days"] < snap["days_left"]:
            if "runway" not in flags:
                flags.add("runway")
                self._row("pool_error", why="runway", runway_days=round(snap["runway_days"], 1),
                          days_left=round(snap["days_left"], 1), loss_per_day=round(snap["loss_per_day"], 2),
                          spare_total=snap["spare_total"])
                out.append(f"POOL RUNWAY: {snap['spare_total']} spare accounts last {snap['runway_days']:.1f} d at "
                           f"{snap['loss_per_day']:.1f} lost/day, {snap['days_left']:.1f} d left. Content is the lever "
                           f"(fewer hides); the pool never raises volume to make up for it.")
        elif snap["runway_days"] >= 1.2 * snap["days_left"]:
            flags.discard("runway")
        return out

    # ---- shadow ------------------------------------------------------------------------------------------------------
    def _do_shadow(self, plan, snap, now):
        """Log what the live worker would do, and apply it to the private copy. Nothing real changes."""
        act = plan["act"]
        with self.mu:
            view = self._view(False)
        rows = {}
        if act == "register":
            v = self._variant(plan["card"], view)
            taken = {r.get("username", "").lower() for r in view} | self.swarm()[2]
            username = variants.username_for(v["handle"], self.rng, taken)
            rec = pool.new_register_record(plan, v, username, "", self.owner, now, self.rng)
            rec.update(status="active")
            rec.pop("password")                                   # the shadow never holds a secret
            self.shadow_new.append(rec)
            rows = dict(username=username, name=v["name"], handle=v["handle"], shape=v.get("shape"), warm_h=plan["warm_h"],
                        checks=v.get("checks") or None)
        else:
            base = next((r for r in view if r.get("username") == plan["username"]), None)
            if base is None:
                return
            rec = dict(base)
            card = variants.card_for(plan["card"])
            if act == "activate":
                v = dict(rec.get("variant") or {})
                if v.get("base") != plan["card"]:
                    v = pool.adopt_identity(self._variant(plan["card"], [r for r in view if r is not base]), rec, card)
                pool.apply_activate(rec, plan, v, now, self.p, self.owner)
            else:
                v = pool.adopt_identity(self._variant(plan["card"], [r for r in view if r is not base]), rec, card)
                pool.apply_convert(rec, plan, v, self._last_holder(plan["card"], view), now, self.p, self.owner)
            for i, x in enumerate(self.shadow_new):
                if x.get("username") == plan["username"]:        # a virtual account the shadow registered earlier
                    self.shadow_new[i] = rec
                    break
            else:
                self.shadow[plan["username"]] = rec
            rows = dict(username=plan["username"], name=rec.get("display_name"), ramp_h=plan.get("ramp_h"),
                        checks=(v.get("checks") or None))
        self.st.after_action(now, self.rng)
        self._remember(f"shadow:{act}", rows.get("username"), now)
        self._row("pool_shadow", would=act, dry_run=True, reason=plan["reason"], state=plan["state"], card=plan["card"],
                  supply=snap["supply"], target=snap["target"], writers=snap["writers"], warming=snap["warming"],
                  alive=snap["alive"], total_used=snap["total_used"], **rows)
        self.say(f"pool (shadow): would {act} {rows.get('username')} on card {plan['card']} [{plan['reason']}]")

    # ---- live --------------------------------------------------------------------------------------------------------
    def _do_live(self, plan, snap, now):
        if self.off_fn():                                         # checked again right before the irreversible step
            return
        if plan["act"] == "register":
            self._register(plan, now)
        else:
            self._local_change(plan, now)

    def _variant(self, card, records):
        """make_variant, retried a bounded number of times while its checks fail; the best one is used, with its reasons."""
        best = None
        for _ in range(VARIANT_TRIES):
            v = variants.make_variant(card, records, self.rng)
            if not v.get("checks"):
                return v
            if best is None or len(v["checks"]) < len(best["checks"]):
                best = v
        return best

    def _last_holder(self, card, view):
        lost = [r for r in view if r.get("persona") == card and pool.status_of(r) != "active"]
        return lost[-1].get("username") if lost else None

    def _find(self, username):
        return next((r for r in self.accounts.records if r.get("username") == username), None)

    def _refresh_stealth(self, now):
        """After any change to the voices: life profiles and N (stealth.refresh); the caller saves once. Holds mu."""
        try:
            return stealth.refresh([r for r in self.accounts.voices() if not self.accounts.parked(r)], now)
        except Exception as e:                                    # noqa: BLE001 - the scheduler refreshes again on its next pick
            self.say(f"pool: stealth.refresh failed: {type(e).__name__}")
            return False

    def _local_change(self, plan, now):
        """activate / convert: no network. A copy of the records is read under mu, the variant made outside it, the change
        validated again and applied under mu, saved once."""
        with self.mu:
            copy = [strip(r) for r in self.accounts.records]
        target = next((r for r in copy if r.get("username") == plan["username"]), None)
        if target is None:
            return
        card = variants.card_for(plan["card"])
        others = [r for r in copy if r is not target]
        if plan["act"] == "convert" or (target.get("variant") or {}).get("base") != plan["card"]:
            new_v = pool.adopt_identity(self._variant(plan["card"], others), target, card)
        else:
            new_v = target["variant"]
        with self.mu:
            rec = self._find(plan["username"])
            snap = self._snapshot(self.accounts.records, now)
            if rec is None or pool.status_of(rec) != "active" or rec.get("username") == self._reporter():
                return
            if plan["act"] == "activate":
                own = (rec.get("variant") or {}).get("base")      # its reserved card counts as free for it
                shape_ok = rec.get("pool_state") == "warming" and plan["card"] in snap["free_cards"] + [own]
            else:
                shape_ok = rec.get("role") == "booster" and not rec.get("pool_state") and plan["card"] in snap["free_cards"]
            if not shape_ok or plan["card"] in snap["held_cards"]:
                return
            if plan["act"] == "activate":
                pool.apply_activate(rec, plan, new_v, now, self.p, self.owner)
            else:
                pool.apply_convert(rec, plan, new_v, self._last_holder(plan["card"], self.accounts.records), now, self.p,
                                   self.owner)
            self._refresh_stealth(now)
            self.accounts.save()
            self.st.after_action(now, self.rng)
            self._remember(plan["act"], rec["username"], now)
            self._row(f"pool_{plan['act']}", username=rec["username"], account_id=rec.get("account_id"), card=plan["card"],
                      reason=plan["reason"], state=plan["state"], ramp_h=plan.get("ramp_h"), name=new_v.get("name"),
                      checks=new_v.get("checks") or None)
        self.say(f"pool: {plan['act']} {plan['username']} on card {plan['card']}")

    def _remember(self, act, username, now):
        self.st.actions.append(dict(ts=pool.iso(now), act=act, username=username))
        del self.st.actions[:-config.POOL_STATUS_ACTS]

    def _reporter(self):
        r = config.blue_reporter(self.accounts.records)
        return r.get("username") if r else None

    def _register(self, plan, now):
        # A. the caps, checked again on the live records, and what the variant needs
        with self.mu:
            snap = self._snapshot(self.accounts.records, now)
            if pool.blockers(snap) or not pool.add_wanted(snap) or plan["card"] not in snap["free_cards"]:
                return
            copy = [strip(r) for r in self.accounts.records]
        # B. the identity, outside mu (CPU only)
        v = self._variant(plan["card"], copy)
        taken = {r.get("username", "").lower() for r in copy} | self.swarm()[2]
        username = variants.username_for(v["handle"], self.rng, taken)
        password = secrets.token_urlsafe(18)
        rec = pool.new_register_record(plan, v, username, password, self.owner, now, self.rng)
        # C. write-ahead: the whole record, status "pending", saved BEFORE the API call
        with self.mu:
            snap = self._snapshot(self.accounts.records, now)           # I1 once more, immediately before the call
            if (pool.blockers(snap) or plan["card"] not in snap["free_cards"] or self.off_fn()
                    or any(r.get("username", "").lower() == username.lower() for r in self.accounts.records)):
                return
            self.accounts.records.append(rec)
            self.accounts.save()
            self.st.after_action(now, self.rng)
            self._row("pool_register", phase="intent", username=username, card=plan["card"], reason=plan["reason"],
                      state=plan["state"], name=v["name"], shape=v.get("shape"), warm_h=plan["warm_h"],
                      checks=v.get("checks") or None)
        # D. the API call, no lock held
        try:
            acc = self.social.register(username, password, self._code, display_name=v["name"])
        except ctn.RateLimited as e:
            self._failed(rec, now, f"429 retry_after={e.retry_after}", blocked=(e.retry_after or 30) + 1 + self.rng.uniform(0, 5))
            return
        except ctn.APIError as e:
            self._register_refused(rec, e, now)
            return
        except NET as e:                                              # outcome unknown: stays pending, reconcile() decides
            with self.mu:
                self.st.blocked_until = now + RECONCILE_RETRY_S
                self._retry[username] = now + RECONCILE_RETRY_S
                self._row("pool_error", why="register_unknown", username=username, detail=type(e).__name__)
            return
        # E. the result
        self._finish(rec, acc, now, reconciled=False, plan=plan)

    def _finish(self, rec, acc, now, reconciled, plan=None):
        with self.mu:
            rec.update(token=acc.token, account_id=acc.account_id, status="active")
            self.accounts.open[rec["username"]] = acc
            self.accounts.save()
            self.st.fails = 0
            self.st.blocked_until = 0.0
            self._remember("register", rec["username"], now)
            self._row("pool_register", phase="done", username=rec["username"], account_id=acc.account_id,
                      card=(rec.get("variant") or {}).get("base"), reconciled=reconciled or None,
                      reason=(plan or {}).get("reason") or (rec.get("pool") or {}).get("reason"),
                      state=(plan or {}).get("state") or (rec.get("pool") or {}).get("state"))
        self.say(f"pool: registered {rec['username']} (id {acc.account_id}), warming"
                 + (" [reconciled]" if reconciled else ""))

    def _failed(self, rec, now, why, blocked=None):
        """The registration did not happen (a clear refusal): the intent record is kept as "failed" for the audit."""
        with self.mu:
            rec["status"], rec["failed_reason"] = "failed", why[:120]
            rec.pop("password", None)
            self.accounts.save()
            if blocked is not None:
                self.st.blocked_until = max(self.st.blocked_until, now + blocked)
            self._row("pool_error", why="register_failed", username=rec["username"], detail=why[:160])

    def _register_refused(self, rec, e, now):
        msg = (e.message or "").lower()
        terminal = e.status == 403 and "total" in msg and "active" not in msg
        with self.mu:
            self.st.fails += 1
            fails = self.st.fails
        if terminal:
            with self.mu:
                self.st.terminal = f"403 {e.message}"[:160]
            self._failed(rec, now, f"403 {e.message}")
            return
        if e.status == 403:
            wait = 3600 if "total" in msg else config.POOL_BACKOFF_S
        else:
            wait = min(config.POOL_BACKOFF_S, 120 * 2 ** (fails - 1))
        self._failed(rec, now, f"{e.status} {e.message}", blocked=wait)
        if fails >= 5 and "register_failing" not in self.st.flags:
            self.st.flags.add("register_failing")
            self.alert(f"POOL: {fails} registrations in a row were refused (last: {e.status} {e.message[:100]}). "
                       f"Backing off {wait // 60:.0f} min between tries.")

    # ---- reconcile (write-ahead recovery) ---------------------------------------------------------------------------
    def reconcile(self, now):
        """Finish or retire ONE pending record per call, by login (read-only on the platform; nothing is created)."""
        with self.mu:
            pend = next((r for r in self.accounts.records if r.get("status") == "pending" and r.get("username")
                         and self._retry.get(r["username"], 0) <= now), None)
            if pend is None:
                return
            username, password = pend["username"], pend.get("password")
            age = now - (pool.parse_ts(pend.get("created")) or now)
            self._retry[username] = now + RECONCILE_RETRY_S
        try:
            acc = self.social.login(username, password)
        except ctn.RateLimited as e:
            self._retry[username] = now + (e.retry_after or 30) + 1
            return
        except ctn.APIError as e:
            msg = (e.message or "").lower()
            if e.status == 403 and "suspend" in msg:
                with self.mu:
                    pend["status"], pend["suspended_at"] = "suspended", pool.iso(now)
                    self.accounts.save()
                    self._row("pool_register", phase="reconciled_suspended", username=username)
            elif e.status in (401, 404):
                if age >= RECONCILE_MIN_AGE_S:
                    self._failed(pend, now, f"reconcile: login {e.status}: the account does not exist")
            return
        except NET:
            return
        self._finish(pend, acc, now, reconciled=True)
