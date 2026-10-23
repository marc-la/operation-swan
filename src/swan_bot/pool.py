"""Pool orchestrator, planning core (todo/38, 2026-10-23). PURE: no network, no files, no clock, no globals.

Everything here takes the account records, the caps, `now` and a random.Random, and returns plain data, so it is tested with
a fake clock and a seeded rng (tests/test_pool.py). The executor that registers, converts and activates for real (or only
logs what it would do) is swan_bot/pool_runner.py; bot.py runs it as the non-critical "pool" worker.

The pool of accounts, by record:
  voice, ramping   role voice, active, rec["ramp"] = {from, until, start}: ready for a write with a chance that rises
                   linearly from `start` (0.25) to 1 until `until` (Accounts.ramp_ok)
  voice, writer    role voice, active, no ramp running
  warming          role "booster", rec["pool_state"] == "warming", rec["warm_until"] (epoch): views and likes only, by the
                   booster routines, until it is activated as a voice on the card rec["variant"]["base"]
  pending          status "pending": the intent record written BEFORE the register call (write-ahead); reconciled by login
  booster          any other active booster (Blue's reporter is one, and is never converted or activated)
  suspended        status "suspended", rec["suspended_at"] (ISO) when known

supply = voices (writers + ramping) + warming. The writer target W* (POOL_WRITERS) and the pipeline P (POOL_PIPELINE):
registration is wanted while supply < W* + P. The state is `healthy` (supply >= W*), `sagging` (< W*) or `low`
(< 0.7 W*). One card per ACTIVE account (Accounts.reserved / by_persona / stealth.key_of assume it): a card is free when no
active voice holds it and no warming account has it reserved. No free card is the expected state until the staged cards are
promoted: the plan then says so (reason "no_free_card") and waits.

Control law (plan_step), the same in shadow and live:
  1. ACTIVATE a warming account whose warm-up has elapsed, while writers < W* (needs a free card: its own reserved one);
  2. else, once the paced delay has passed: in sagging/low CONVERT a booster (spends no total slot) before registering;
  3. else REGISTER a warming account (variant of a free card), if supply < W* + P, alive + 1 <= 49, total + 1 <= 200.
  One action at a time, at least POOL_FLOOR_S (15 min; POOL_FLOOR_LOW_S, 8 min, when low) after the previous one of any kind.
  The warm-up hours and the ramp hours use the worse of the supply state and the state of the writers alone (voices < 0.85 W*,
  POOL_FAST_FRAC: warming accounts do not write yet): a pool whose writers sag but whose pipeline is full warms its next
  accounts for 1 to 4 h, not 3 to 12 (simulation, 38 losses a day: the long warm-up was what let the writers sag).
  The floors always follow the supply state.
  The delay before a convert/register is exp(ln median(deficit) + sigma z), z drawn once per action: 5 h median when healthy
  (one replacement per loss, counted from when the want arose), 30 min at a 30% deficit, 10 min at 100%; a given z only ever
  gets shorter as the deficit grows. A 429 waits its Retry-After; a 403 for the total allowance is terminal.
"""
import datetime as dt
import math
import random
from dataclasses import dataclass, field

STATES = ("healthy", "sagging", "low")
Z_CLIP = (-2.0, 2.5)
ACTS = ("activate", "convert", "register")


@dataclass
class Params:
    """The control law's numbers. Params.from_config() reads swan_bot.config; tests build their own."""
    writers: int = 31
    pipeline: int = 4
    alive_cap: int = 49
    total_cap: int = 200
    floor_s: float = 15 * 60
    floor_low_s: float = 8 * 60
    low_frac: float = 0.7
    fast_frac: float = 0.85
    median_pts: tuple = ((0.0, 5 * 3600), (0.1, 45 * 60), (0.3, 15 * 60), (1.0, 8 * 60))
    sigma: float = 0.7
    delay_max_s: float = 18 * 3600
    warm_h: dict = field(default_factory=lambda: dict(healthy=(6, 36), sagging=(3, 12), low=(1, 4)))
    ramp_h: dict = field(default_factory=lambda: dict(healthy=(60, 72), sagging=(48, 60), low=(36, 48)))
    ramp_start: float = 0.25
    convert_ramp_h: dict = field(default_factory=lambda: dict(healthy=(24, 36), sagging=(12, 24), low=(6, 12)))
    loss_window_s: float = 72 * 3600
    loss_half_life_s: float = 24 * 3600
    runway_min_loss: float = 0.5
    card_cooldown_s: float = 12 * 3600
    end_iso: str = "2026-11-03T00:00:00+11:00"

    @classmethod
    def from_config(cls, config):
        return cls(writers=config.POOL_WRITERS, pipeline=config.POOL_PIPELINE, alive_cap=config.MAX_ACTIVE,
                   total_cap=config.POOL_TOTAL_CAP, floor_s=config.POOL_FLOOR_S, floor_low_s=config.POOL_FLOOR_LOW_S,
                   low_frac=config.POOL_LOW_FRAC, fast_frac=config.POOL_FAST_FRAC, median_pts=tuple(tuple(x) for x in config.POOL_MEDIAN_PTS),
                   sigma=config.POOL_DELAY_SIGMA, delay_max_s=config.POOL_DELAY_MAX_S, warm_h=dict(config.POOL_WARM_H),
                   ramp_h=dict(config.POOL_RAMP_H), ramp_start=config.POOL_RAMP_START,
                   convert_ramp_h=dict(config.POOL_CONVERT_RAMP_H),
                   loss_window_s=config.POOL_LOSS_WINDOW_S, loss_half_life_s=config.POOL_LOSS_HALF_LIFE_S,
                   runway_min_loss=config.POOL_RUNWAY_MIN_LOSS, card_cooldown_s=config.POOL_CARD_COOLDOWN_S,
                   end_iso=config.POOL_END)


@dataclass
class PoolState:
    """What the worker remembers between ticks (memory only; a restart reads last_action_ts back from the records)."""
    last_action_ts: float = 0.0
    z: float = 0.0
    want_since: float = None            # when the want to add (register/convert) arose; None while there is none
    blocked_until: float = 0.0          # a 429's Retry-After, or a failed register's backoff
    terminal: str = None                # set by a 403 for the total allowance: no more registering, ever
    fails: int = 0                      # failed registers in a row
    actions: list = field(default_factory=list)   # [{ts, act, username}], newest last
    flags: set = field(default_factory=set)       # alerts already sent (once each)

    def after_action(self, now, rng):
        self.last_action_ts, self.want_since, self.z = now, None, draw_z(rng)


def draw_z(rng):
    return min(max(rng.gauss(0.0, 1.0), Z_CLIP[0]), Z_CLIP[1])


# ---- small helpers --------------------------------------------------------------------------------------------------
def parse_ts(v):
    """Epoch seconds from an ISO string or a number, else None."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        d = dt.datetime.fromisoformat(str(v))
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).timestamp()


def iso(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat()


def status_of(r):
    return r.get("status", "active")


def is_voice(r):
    return r.get("role", "voice") != "booster"


def days_left(now, end_iso):
    """Days from now to the competition's end (not below 0)."""
    end = parse_ts(end_iso)
    return max(0.0, (end - now) / 86400.0) if end is not None else 0.0


def deficit_of(supply, target):
    return max(0.0, (target - supply) / target) if target > 0 else 0.0


def state_of(supply, target, low_frac):
    if supply >= target:
        return "healthy"
    return "low" if supply < low_frac * target else "sagging"


def floor_s(state, p):
    return p.floor_low_s if state == "low" else p.floor_s


def median_delay_s(deficit, p):
    """Median wait before the next add: log-linear between the (deficit, seconds) points of p.median_pts."""
    d = min(max(deficit, 0.0), 1.0)
    pts = p.median_pts
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if d <= x1:
            u = (d - x0) / (x1 - x0) if x1 > x0 else 1.0
            return math.exp(math.log(y0) + u * (math.log(y1) - math.log(y0)))
    return float(pts[-1][1])


def delay_s(deficit, z, p, state=None):
    """The wait before the next add for the draw z: median x exp(sigma z), at least the state's floor, at most delay_max_s."""
    state = state or state_of(p.writers * (1 - deficit), p.writers, p.low_frac)
    raw = median_delay_s(deficit, p) * math.exp(p.sigma * z)
    return min(max(raw, floor_s(state, p)), max(p.delay_max_s, floor_s(state, p)))


def loss_rate_per_day(ts, now, p):
    """Accounts lost per day: an exponentially weighted count of the suspensions in the last loss_window_s (half-life
    loss_half_life_s), divided by the same weighting of a window that is full of events at a constant rate, so a steady
    13 a day reads 13."""
    h, w = p.loss_half_life_s, p.loss_window_s
    k = math.log(2) / h
    total = sum(math.exp(-k * (now - t)) for t in ts if 0 <= now - t <= w)
    norm = (1 - math.exp(-k * w)) / k
    return total / norm * 86400.0 if norm else 0.0


def runway_days(spare_total, loss_per_day, p):
    return spare_total / max(loss_per_day, p.runway_min_loss)


# ---- the snapshot -----------------------------------------------------------------------------------------------------
def snapshot(records, now, p, *, cards=(), swarm_alive=0, swarm_used=0, suspended_ts=None, reporter=None, st=None):
    """Counts and candidate lists for the control law, from the account records (read only). cards: the card keys that
    may be given to a new voice (content.PERSONAS). suspended_ts: {username: epoch} for suspensions whose record has no
    suspended_at. reporter: Blue's reporter's username (never converted or activated). st: the PoolState."""
    st = st or PoolState()
    suspended_ts = suspended_ts or {}
    recs = list(records)
    voices = [r for r in recs if status_of(r) == "active" and is_voice(r)]
    ramping = [r for r in voices if (r.get("ramp") or {}).get("until", 0) > now]
    warm = [r for r in recs if r.get("pool_state") == "warming" and status_of(r) in ("active", "pending") and not is_voice(r)]
    held = {r["persona"] for r in voices if r.get("persona")}
    reserved = {(r.get("variant") or {}).get("base") for r in warm} - {None}
    lost = []
    for r in recs:
        if status_of(r) == "suspended":
            t = parse_ts(r.get("suspended_at"))
            t = suspended_ts.get(r.get("username")) if t is None else t
            if t is not None and 0 <= now - t <= p.loss_window_s:
                lost.append(dict(username=r.get("username"), ts=t, card=r.get("persona")))
    alive = sum(1 for r in recs if status_of(r) in ("active", "pending")) + swarm_alive
    total_used = sum(1 for r in recs if status_of(r) != "failed") + swarm_used
    supply = len(voices) + len(warm)
    state = state_of(supply, p.writers, p.low_frac)
    wstate = state_of(len(voices), p.writers, p.fast_frac)      # the writers alone (fast mode under fast_frac x W*)
    deficit = deficit_of(supply, p.writers)
    free = sorted(k for k in cards if k not in held and k not in reserved)
    fresh_loss = {x["card"] for x in lost if x["card"] and now - x["ts"] < p.card_cooldown_s}
    ready = sorted((dict(username=r["username"], base=(r.get("variant") or {}).get("base"), warm_until=r.get("warm_until", 0))
                    for r in warm if status_of(r) == "active" and r.get("warm_until", 0) <= now
                    and r.get("username") != reporter), key=lambda x: x["warm_until"])
    convertible = sorted(r["username"] for r in recs if status_of(r) == "active" and r.get("role") == "booster"
                         and not r.get("pool_state") and r.get("account_id") and r.get("username") != reporter)
    loss = loss_rate_per_day([x["ts"] for x in lost], now, p)
    spare = max(0, p.total_cap - total_used)
    last = max([st.last_action_ts] + [parse_ts((r.get("pool") or {}).get("at")) or 0.0 for r in recs])
    return dict(
        now=now, target=p.writers, pipeline=p.pipeline, state=state, deficit=deficit, supply=supply,
        wstate=wstate,
        writers=len(voices) - len(ramping), ramping=len(ramping), voices=len(voices), warming=len(warm),
        ready=ready, convertible=convertible, held_cards=sorted(held), reserved_cards=sorted(reserved), free_cards=free,
        fresh_loss_cards=sorted(fresh_loss), alive=alive, alive_cap=p.alive_cap, total_used=total_used,
        total_cap=p.total_cap, spare_total=spare, losses=lost, loss_per_day=loss, runway_days=runway_days(spare, loss, p),
        days_left=days_left(now, p.end_iso), last_action_ts=last, want_since=st.want_since, z=st.z,
        blocked_until=st.blocked_until, terminal=st.terminal)


def add_wanted(snap):
    """Does the pool want one more account (a register, or a conversion)? supply < W* + P, and nothing in the way."""
    return snap["supply"] < snap["target"] + snap["pipeline"]


def blockers(snap):
    """Why a register cannot be done now: a list of reasons ([] = it can)."""
    why = []
    if snap["terminal"]:
        why.append("total_cap_403")
    if snap["total_used"] + 1 > snap["total_cap"]:
        why.append("total_cap")
    if snap["alive"] + 1 > snap["alive_cap"]:
        why.append("alive_cap")
    if not snap["free_cards"]:
        why.append("no_free_card")
    return why


def add_due_ts(snap, p):
    """Epoch time before which no register/convert is done: the later of the last action and the moment the want arose,
    plus the paced delay for the current deficit and this action's draw."""
    base = max(snap["last_action_ts"], snap["want_since"] if snap["want_since"] is not None else snap["now"])
    return base + delay_s(snap["deficit"], snap["z"], p, snap["state"])


def choose_card(snap, rng):
    """A free card, preferring one whose last voice was not suspended within the cooldown; None if there is none."""
    free = snap["free_cards"]
    calm = [k for k in free if k not in snap["fresh_loss_cards"]]
    pool = calm or free
    return rng.choice(sorted(pool)) if pool else None


def _hours(table, state, rng):
    lo, hi = table[state]
    return round(rng.uniform(lo, hi), 2)


def plan_step(snap, now, rng, p):
    """The one action to take now, or None. Pure (the rng is the only thing it advances). Returns a dict:
      act      "activate" | "convert" | "register"
      reason   why, in words (logged as `reason`)
      state    healthy | sagging | low
      card     the card key (the account's reserved card for activate)
      username the account acted on (activate, convert); absent for register
      warm_h   (register) hours of warm-up; ramp_h (activate, convert) hours of ramp
    Never two actions closer than the state's floor; never past a cap; convert before register."""
    state = snap["state"]
    if now - snap["last_action_ts"] < floor_s(state, p):
        return None
    base = dict(state=state)
    wstate = max(state, snap["wstate"], key=STATES.index)   # warm-up and ramp follow the WRITERS too (worse of the two)
    # 1. a warmed account becomes a voice
    if snap["voices"] < snap["target"]:
        for c in snap["ready"]:
            card = c["base"] if c["base"] and c["base"] not in snap["held_cards"] else None
            if card is None:
                card = choose_card(snap, rng)           # its own card was taken meanwhile: another free one
            if card is None:
                continue
            return dict(base, act="activate", username=c["username"], card=card, ramp_h=_hours(p.ramp_h, wstate, rng),
                        reason=f"warm-up done, writers {snap['voices']} < {snap['target']}")
    if not add_wanted(snap) or now < add_due_ts(snap, p):
        return None
    # 2. convert before register, once the pool is under target (a conversion spends no total slot)
    if state != "healthy" and snap["convertible"] and snap["free_cards"] and snap["voices"] < snap["target"]:
        card = choose_card(snap, rng)
        return dict(base, act="convert", username=rng.choice(snap["convertible"]), card=card,
                    ramp_h=_hours(p.convert_ramp_h, wstate, rng),           # an aged booster: a shorter ramp than a fresh account
                    reason=f"{state}: supply {snap['supply']} < {snap['target']}, convert before register")
    # 3. register a warming account (a 429's Retry-After and a failed register's backoff hold only this: conversion and
    # activation are local)
    if blockers(snap) or now < snap["blocked_until"]:
        return None
    card = choose_card(snap, rng)
    why = (f"{state}: supply {snap['supply']} < {snap['target']}" if state != "healthy"
           else f"healthy: replacement, supply {snap['supply']} < {snap['target']} + {snap['pipeline']}")
    return dict(base, act="register", card=card, warm_h=_hours(p.warm_h, wstate, rng), reason=why)


def waiting_reason(snap, p, now):
    """Why plan_step has nothing to do now (for the log and the alert-once cases), or None when it has an action or the pool
    is simply full."""
    if not add_wanted(snap) and not snap["ready"]:
        return None
    if snap["terminal"]:
        return "total_cap_403"
    if add_wanted(snap):
        b = blockers(snap)
        if "no_free_card" in b and not (snap["ready"] and snap["voices"] < snap["target"]):
            return "no_free_card"
        if "alive_cap" in b:
            return "alive_cap"
        if "total_cap" in b:
            return "total_cap"
    return None


# ---- records: build and change (pure) ---------------------------------------------------------------------------------
def pool_note(act, reason, state, now, owner, card=None):
    return dict(by="pool", act=act, at=iso(now), reason=reason, state=state, owner=owner, card=card)


def new_register_record(action, variant, username, password, owner, now, rng):
    """The write-ahead record of a registration: complete before the API call, status "pending". A warming account is a
    booster (the booster routines give it views and likes) that holds the variant's base card in reserve."""
    return dict(role="booster", persona=None, username=username, display_name=variant["name"], owner=owner,
                created=iso(now), status="pending", pool_state="warming",
                warm_until=round(now + action["warm_h"] * 3600, 1), variant=variant, password=password,
                sleep_start=round(rng.uniform(0, 24), 2), last_write=0, writes=0, followed=[],
                pool=pool_note("register", action["reason"], action["state"], now, owner, variant["base"]))


def ramp_for(now, hours, p):
    return dict(**{"from": round(now, 1)}, until=round(now + hours * 3600, 1), start=p.ramp_start)


def apply_activate(rec, action, variant, now, p, owner):
    """A warmed account becomes a voice on `variant["base"]`. In place."""
    rec.update(role="voice", persona=variant["base"], variant=variant, pool_state="active",
               ramp=ramp_for(now, action["ramp_h"], p), pool=pool_note("activate", action["reason"], action["state"], now, owner,
                                                                       variant["base"]))
    rec.pop("warm_until", None)
    return rec


def apply_convert(rec, action, variant, old_holder, now, p, owner):
    """A like-only booster becomes a voice on a free card under a variant. It keeps its username, display name and
    history. `converted` keeps the old audits (pattern_audit reads converted.at) and stealth.key_of working. In place."""
    rec.update(role="voice", persona=variant["base"], variant=variant, pool_state="active",
               ramp=ramp_for(now, action["ramp_h"], p),
               converted=dict(at=iso(now), by="pool", from_role="booster", card_of=old_holder,
                              style_of=variant.get("style_of")),
               pool=pool_note("convert", action["reason"], action["state"], now, owner, variant["base"]))
    return rec


def adopt_identity(variant, rec, card):
    """Make a variant fit an account that already exists: its display name and username stay, so the voice drafts under the
    name the platform shows. `card`: the base card dict (its own name is swapped for the account's). Returns the variant."""
    name = (rec.get("display_name") or rec.get("username") or "").strip()
    parts = name.split()
    first = parts[0] if parts else name
    last = parts[1] if len(parts) > 1 and not parts[1].endswith(".") else ""
    full = f"{first} {last}".strip()
    swap = dict(variant.get("swap") or {})
    if card.get("name"):
        swap[card["name"]] = full
        swap[card["name"].split()[0]] = first
    variant.update(name=name or first, first=first, last=last, handle=rec.get("username") or variant.get("handle"), swap=swap)
    return variant


# ---- the status block for data/status.json["pool"] ------------------------------------------------------------------
def status_dict(snap, st, p, now, dry_run, off=False):
    """Exactly the keys swan_dash.build.pool_view reads. Numbers are real numbers; next_add_in_min is None only when
    nothing can be added (blocked), which the dashboard leaves out."""
    can_convert = (snap["state"] != "healthy" and snap["convertible"] and snap["free_cards"]
                   and snap["voices"] < snap["target"])
    blocked = not (can_convert or not blockers(snap))
    nxt = None if blocked or not add_wanted(snap) else round(max(0.0, max(add_due_ts(snap, p), snap["blocked_until"],
                                                                         snap["last_action_ts"] + floor_s(snap["state"], p)) - now) / 60.0, 1)
    n = lambda x: float(x) if isinstance(x, float) else int(x)
    return dict(
        dry_run=bool(dry_run or off), state=snap["state"], writers_target=n(snap["target"]), writers=n(snap["writers"]),
        ramping=n(snap["ramping"]), warming=n(snap["warming"]), alive=n(snap["alive"]), alive_cap=n(snap["alive_cap"]),
        total_used=n(snap["total_used"]), total_cap=n(snap["total_cap"]), spare_total=n(snap["spare_total"]),
        loss_per_day=round(snap["loss_per_day"], 2), runway_days=round(snap["runway_days"], 1),
        days_left=round(snap["days_left"], 2), next_add_in_min=nxt,
        last_actions=[dict(a) for a in st.actions[-8:]])
