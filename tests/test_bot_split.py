"""todo/22: the reader/writer split runs everything the serial loop ran, and keeps its rules.

Each run is bot.main() end to end against a fake Legit Social (FakeWorld below) with a fake LLM, in "live" mode so the
reply-back poll, the status file and the saved state run too. Nothing can reach the network: every socket connect
raises (no_network), the team code is a dummy, and all files go to a temp dir. Gaps and pacing are shrunk so a run
takes seconds. The same world runs with config.SPLIT_LOOP on and off: the old loop must pass the same checklist.

Checklist (todo/22 "Assurance" 1): job types reply, reply_back, second_voice, journalist, post, repost; duties:
registration, pulse.update, the fact desk (facts.refresh), amp.tick, write_status, save_state, the hidden-post limit,
the todo/20 and todo/21 logging (requeue / lost, skip(read), the refresh funnel, read_* fields).
Rules (2): only the writer posts; pacing never faster than pace_gap and a 429 backs off; the voice gaps hold; no double
replies; each state file has one writer and is replaced atomically. Then the watchdog and the clean stop.
"""
import collections
import datetime as dt
import itertools
import json
import math
import os
import pathlib
import signal
import socket
import sys
import threading
import time

import pytest

pytestmark = pytest.mark.slow  # runs bot.main() on the fake world, ~12 s per variant

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import capturethenarrative as ctn  # noqa: E402

from swan_bot import amplify, bot, config, content, facts, feeds, pulse, watch  # noqa: E402
from swan_bot import targeting  # noqa: E402

GAP = 0.3                 # pace_gap in these runs (s)
VOICE_GAP = 0.5           # ACCOUNT_MIN_GAP_S
REPOST_GAP = 0.2          # REPOST_MIN_GAP_S
REPLY_BACK_GAP = 0.4      # bot.REPLY_BACK_GAP_S
RETRY_AFTER = 1           # the one 429 the world answers (on the first journalist reply)
RUN_S = 12                # a run's --hours, in seconds
VOICES = 6                # seeded voices; the last is parked (HIDDEN_STOP hidden posts)
DRAFTER_NAMES = {f"drafter-{i}" for i in range(1, config.DRAFTERS + 1)}
JOB_TYPES = {"reply", "reply_back", "second_voice", "journalist", "post", "repost"}
STEALTH_RULES = ("VOICE_DAY_CAP", "VOICE_HOUR_CAP", "VOICE_SLEEP", "VOICE_JITTER", "VOICE_STAGGER", "ONE_VOICE_PER_CITIZEN")


def iso(t=None):
    return dt.datetime.fromtimestamp(t or time.time(), dt.timezone.utc).isoformat()


class FakeWorld:
    """Posts, notifications and every write, in memory. Writes are recorded with the thread that made them."""

    def __init__(self):
        self.lock = threading.Lock()
        self.posts, self.next_id, self.notes = {}, 10_000, {}
        self.writes = []              # dicts: t, thread, kind, username, target, post_id
        self.reads = []               # thread names of feed reads
        self.answered_back = False    # citizen 501 answers our first reply to them, once
        self.limited = False          # the one 429 has been answered
        self.accounts = {}            # token -> record (filled from the seeded accounts file)
        self.add(100, 1, "Referendum on the H2D2 vaccination pass: what the vote means for venues")
        self.add(201, 501, "Not sure about the vaccination pass, what about people with medical exemptions?", 100)
        self.add(202, 502, "Undecided on the referendum, does the pass ever end or is it forever?", 100)
        self.add(203, 503, "LOSE-ME: the vaccine pass referendum worries me, the venue checks sound awful", 100)
        self.add(204, 504, "SKIP-ME: heard the referendum vote is soon, is the pass a good idea?", 100)
        self.add(210, 505, "Still deciding how to vote on the referendum. Is the health pass really needed?")
        self.add(300, 3, "Polling day nears: what voters say about the referendum and the vaccination pass")
        self.add(900, 3001, "Keep Kingstonia open: our venues, our choice. Voting No.")

    def add(self, pid, author, body, parent=None, kind=None):
        root = None
        if parent:
            root = self.posts[parent].get("root_post_id") or parent
        self.posts[pid] = dict(post_id=pid, author_id=author, body=body, created_at=iso(), reply_to_post_id=parent,
                               root_post_id=root, kind=kind or ("reply" if parent else "post"))
        return self.posts[pid]

    def write(self, rec, kind, target=None, body=None):
        with self.lock:
            if kind == "reply" and self.posts.get(target, {}).get("author_id") == 3 and not self.limited:
                self.limited = True
                self.writes.append(dict(t=time.time(), thread=threading.current_thread().name, kind="429",
                                        username=rec["username"], target=target, post_id=None))
                raise ctn.RateLimited("POST", "/posts", 429, "{}", RETRY_AFTER)
            self.next_id += 1
            pid = self.next_id
            if kind in ("post", "reply", "repost"):
                self.add(pid, rec["account_id"], body or "", target if kind == "reply" else None,
                         kind="repost" if kind == "repost" else None)
            self.writes.append(dict(t=time.time(), thread=threading.current_thread().name, kind=kind,
                                    username=rec["username"], target=target, post_id=pid))
            if kind == "reply" and self.posts.get(target, {}).get("author_id") == 501 and not self.answered_back:
                self.answered_back = True              # the citizen answers us: a reply-back job for this voice
                self.next_id += 1
                self.add(self.next_id, 501, "Fair point about the exemptions, but how would you vote then?", pid)
                self.notes.setdefault(rec["username"], []).append(
                    dict(notification_id=self.next_id, kind="reply", post=dict(post_id=self.next_id)))
            return dict(post_id=pid)


class FakeAccount:
    def __init__(self, world, rec):
        self.world, self.rec = world, rec
        self.rate_limit = ctn.RateLimit(3, 2, 60)

    @property
    def account_id(self):
        return self.rec["account_id"]

    def post(self, body):
        return self.world.write(self.rec, "post", body=body)

    def reply(self, post_id, body):
        return self.world.write(self.rec, "reply", post_id, body)

    def repost(self, post_id):
        return self.world.write(self.rec, "repost", post_id)

    def follow(self, account_id):
        self.world.write(self.rec, "follow", account_id)

    def view(self, post_id):
        self.world.write(self.rec, "view", post_id)

    def like(self, post_id):
        self.world.write(self.rec, "like", post_id)

    def notifications(self, unresolved=False, limit=50):
        return list(self.world.notes.get(self.rec["username"], []))[:limit]

    def resolve_notification(self, nid):
        notes = self.world.notes.get(self.rec["username"], [])
        notes[:] = [n for n in notes if n["notification_id"] != nid]


class FakeSocial:
    """The read side of ctn.LegitSocial over a FakeWorld; account_from_token gives a FakeAccount."""

    def __init__(self, world):
        self.world, self.rate_limit = world, None

    def feed_lock(self):
        return {"locked": False}

    def _page(self, posts):
        self.world.reads.append(threading.current_thread().name)
        return ctn.Page(posts, None)

    def feed_latest(self, limit=100, cursor=None):
        return self._page([] if cursor else sorted((p for p in self.world.posts.values() if p["post_id"] == 210),
                                                   key=lambda p: -p["post_id"]))

    def feed_trending(self, limit=50, cursor=None):
        return self._page([])

    def account_posts(self, account_id, limit=50, cursor=None):
        return ctn.Page([p for p in self.world.posts.values() if p["author_id"] == account_id
                         and not p["reply_to_post_id"]][:limit])

    def replies(self, post_id, limit=50, cursor=None):
        return ctn.Page([p for p in list(self.world.posts.values()) if p["reply_to_post_id"] == post_id][:limit])

    def get_post(self, post_id):
        if post_id not in self.world.posts:
            raise ctn.APIError("GET", f"/posts/{post_id}", 404, "{}")
        return dict(self.world.posts[post_id])

    def get_account(self, account_id):
        return {}

    def account_from_token(self, token):
        return FakeAccount(self.world, self.world.accounts[token])

    def login(self, username, password):
        rec = next(r for r in self.world.accounts.values() if r["username"] == username)
        return FakeAccount(self.world, rec)

    def register(self, username, password, code, display_name=None):
        rec = dict(username=username, account_id=4000 + len(self.world.accounts), token=f"tok-{username}")
        self.world.accounts[rec["token"]] = rec
        acc = FakeAccount(self.world, rec)
        acc.token = rec["token"]
        return acc

    def __getattr__(self, name):            # anything else the amplifier reads: nothing there
        return lambda *a, **kw: ctn.Page([])


class FakeGen:
    chain, calls, on_park = [], {}, None

    def __init__(self, *a, **kw):
        pass

    def describe(self):
        return "fake"

    def status(self):
        return []

    def next_available_in(self):
        return 0.0

    def no_model_wait(self, priority=False, models=None):
        return 0.0

    def complete(self, system, user, **kw):
        return "{}", "fake"


FAKE_TEXTS = itertools.count()
FAKE_OPENERS = ["Honestly I'm voting No on this one", "Look, my partner runs a cafe and this pass would sink her",
                "Three weeks of queues at the clinic taught me plenty", "Fair question, and my answer stays No",
                "Everyone at our footy club says the same thing", "My nan can't use a phone, so how does she get in",
                "Rules without an end date worry me far more", "Speaking as a nurse, venue checks fix nothing"]


def fake_draft_checked(gen, job, system, user, recent_texts, on_reject=None, ledger=None):
    """A draft per job without an LLM: LOSE-ME targets fail the gate, SKIP-ME targets are skipped by the light read."""
    body = (job.get("target") or {}).get("body") or ""
    meta = job.setdefault("meta", {})
    meta.update(llm_calls=1, repairs=0, fixes=[])
    if "LOSE-ME" in body:
        meta["last_reject"] = "length_400"
        if on_reject:
            on_reject("length_400", "a draft that is far too long", "fake", None)
        return None, "fake", None
    if "SKIP-ME" in body and job.get("read"):
        job["read_skip"] = "not really about the vote"
        return None, "fake", None
    if job.get("read"):
        meta.update(read_ok=True, read_stance="unsure", read_doubt="exemptions", read_frame=None, read_skip=None)
    # a different opening and wording each time, as the real gate demands of the drafts waiting (same_opening,
    # near_duplicate): bot.clashes_with_ready drops a concurrent draft that repeats one waiting for the writer
    n = next(FAKE_TEXTS) % len(FAKE_OPENERS)
    return f"{FAKE_OPENERS[n]} ({job['mode']} {job['draft_id']}).", "fake", None


class Spy:
    """Counts calls (and the threads they came from) and passes them on."""

    def __init__(self, fn):
        self.fn, self.calls, self.threads = fn, 0, set()

    def __call__(self, *a, **kw):
        self.calls += 1
        self.threads.add(threading.current_thread().name)
        return self.fn(*a, **kw)


def block_network(mp):
    """Every socket connect fails: nothing in these tests can reach Legit Social, an LLM or a webhook."""
    def refuse(*a, **kw):
        raise OSError("tests/test_bot_split.py: no network in tests")
    mp.setattr(socket.socket, "connect", refuse)
    mp.setattr(socket.socket, "connect_ex", refuse)
    mp.setattr(socket, "create_connection", refuse)


@pytest.fixture
def no_network(monkeypatch):
    block_network(monkeypatch)


def setup_world(mp, tmp, split, amp_off=False):
    """Point every file at tmp, seed accounts and state, and swap in the fakes. Returns (world, spies)."""
    world = FakeWorld()
    logs, data, secrets = tmp / "logs", tmp / "data", tmp / "secrets"
    for d in (logs, data, secrets):
        d.mkdir(exist_ok=True)
    for mod, attr, val in ((config, "LOGS", logs), (config, "DATA", data), (config, "ACTIONS_LOG", logs / "actions.jsonl"),
                           (config, "STATE_FILE", data / "swan_state.json"), (config, "STATUS_FILE", data / "status.json"),
                           (config, "ACCOUNTS_FILE", secrets / "swan_accounts.json"),
                           (config, "AMP_OFF_FILE", tmp / "AMPLIFY_OFF"), (feeds, "FEED_LOG", logs / "feed_reads.jsonl"),
                           (feeds, "SNAPSHOT_FILE", data / "latest_snapshot.json"), (watch, "WATCH_FILE", data / "watch.json")):
        mp.setattr(mod, attr, val)
    if amp_off:
        (tmp / "AMPLIFY_OFF").touch()
    for attr, val in (("SPLIT_LOOP", split), ("ACCOUNT_MIN_GAP_S", VOICE_GAP), ("REPOST_MIN_GAP_S", REPOST_GAP),
                      ("NOTIF_EVERY_S", 0.3), ("REFRESH_S", 0.5), ("REGISTER_GAP_S", (3600, 3600)),
                      ("SECOND_VOICE", True),     # off live since 22 Oct (stealth); the checklist still exercises it
                      ("SECOND_VOICE_ARMS", {"fast": (0, 0.05), "slow": (0, 0.05)}), ("OWN_LIKE_DELAY_S", (0, 0.05)),
                      ("ENG_FOLLOW_DELAY_S", (0, 0.05)), ("ENG_LIKE_DELAY_S", (0, 0.05)),
                      ("ENG_BUDGET_MARGIN", 0),     # the fake account reports the write route (3/min) after every call
                      ("AMP_PRIORITY_S", 0), ("READER_SILENT_S", 30), ("DRAFTER_SILENT_S", 30)):
        mp.setattr(config, attr, val)
    # todo/31's human day is off here (the checklist needs second voices and many writes in 12 s); it runs end to end
    # with these worlds in tests/test_stealth.py
    for attr in STEALTH_RULES:
        mp.setattr(config, attr, False)
    mp.setattr(config, "load_env", lambda *a, **kw: None)
    mp.setattr(config, "assigned_side", lambda: "no")
    mp.setattr(config, "team_code", lambda: "dummy-team-code")
    mp.setattr(config, "operator", lambda: "tester")
    mp.setattr(bot, "REPLY_BACK_GAP_S", REPLY_BACK_GAP)
    mp.setattr(bot, "IDLE_S", 0.05)
    mp.setattr(bot, "JOIN_S", 3.0)
    mp.setattr(bot, "WAIT_S", dict(no_voice=0.2, nothing=0.2, priority=0.2))
    mp.setattr(bot, "pace_gap", lambda per_min: GAP)
    mp.setattr(bot, "Generator", FakeGen)
    mp.setattr(bot, "draft_checked", fake_draft_checked)
    mp.setattr(ctn, "LegitSocial", lambda *a, **kw: FakeSocial(world))
    alerts = []
    mp.setattr(bot, "alert", alerts.append)

    personas = [p["key"] for p in content.PERSONAS[:VOICES]]
    recs = [dict(persona=k, username=f"u{i}", password="pw", token=f"tok-u{i}", account_id=3001 + i, owner="tester",
                 status="active", last_write=0, writes=0, followed=[], role="voice") for i, k in enumerate(personas)]
    for r in recs:
        world.accounts[r["token"]] = r
    (secrets / "swan_accounts.json").write_text(json.dumps(recs))
    watch.save({"hidden": {f"u{VOICES - 1}": [1, 2]}}, path=data / "watch.json")        # parked: HIDDEN_STOP = 2
    # an old amplified post of voice u0 with a repost due now (the amplifier's thread jobs)
    (data / "swan_state.json").write_text(json.dumps(dict(
        amp_posts={"900": dict(t=time.time() - 3600, persona=personas[0], text="Keep Kingstonia open.")},
        amp_threads=[dict(kind="repost", post_id=900, due=time.time(), author=personas[0], frame="F14_no_yes_but")])))

    spies = dict(save_json=[], snapshot=[])
    real_save, real_snap = bot.save_json, feeds.write_snapshot
    mp.setattr(bot, "save_json", lambda path, obj, private=False: (
        spies["save_json"].append((str(path), threading.current_thread().name)), real_save(path, obj, private))[1])
    mp.setattr(feeds, "write_snapshot", lambda *a, **kw: (
        spies["snapshot"].append((str(kw.get("path")), threading.current_thread().name)), real_snap(*a, **kw))[1])
    for name, owner, attr in (("pulse", pulse, "update"), ("facts", facts, "refresh"),
                              ("refresh", targeting.Targeter, "refresh"), ("amp_tick", amplify.Amplifier, "tick"),
                              ("reply_backs", bot, "reply_back_jobs"), ("own_likes", bot, "own_likes"),
                              ("register", bot.Accounts, "maybe_register")):
        spies[name] = spy = Spy(getattr(owner, attr))
        if isinstance(owner, type):         # a method: a plain function keeps self
            mp.setattr(owner, attr, lambda self, *a, _spy=spy, **kw: _spy(self, *a, **kw))
        else:
            mp.setattr(owner, attr, spy)
    spies["alerts"] = alerts
    return world, spies


def run_main(mp, seconds=RUN_S, extra=()):
    hours = seconds / 3600
    mp.setattr(sys, "argv", ["swan_bot", "--live", "--yes", "--accounts", str(VOICES + 1), "--per-min", "2.5",
                             "--amplify", "--hours", f"{hours:.6f}", *extra])
    bot.main()


def actions(tmp):
    path = tmp / "logs" / "actions.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


@pytest.fixture(scope="module", params=[True, False], ids=["split", "serial"])
def run(request, tmp_path_factory):
    """One end-to-end run per loop, shared by the checklist and rule tests below."""
    tmp = tmp_path_factory.mktemp("split" if request.param else "serial")
    with pytest.MonkeyPatch.context() as mp:
        block_network(mp)
        world, spies = setup_world(mp, tmp, request.param)
        run_main(mp)
    return dict(split=request.param, tmp=tmp, world=world, spies=spies, acts=actions(tmp))


# ---- todo/33: the free levers (follow, like) run through the same loops, each cell doing exactly its actions ----
def test_engagement_levers_follow_the_citizens_cell(run):
    from swan_bot import engage
    acts = run["acts"]
    replies = [a for a in acts if a["act"] in ("reply", "reply_back", "second_voice") and a.get("post_id")
               and a.get("target_author")]
    assert replies and all(a.get("eng_cell") == engage.cell(a["target_author"]) for a in replies)
    levers = [a for a in acts if a.get("purpose") in ("eng_follow", "eng_like")]
    assert {a["purpose"] for a in levers} >= {"eng_follow", "eng_like"}, "both levers ran"
    state = json.loads((run["tmp"] / "data" / "swan_state.json").read_text())
    assert isinstance(state["eng_queue"], list) and isinstance(state["eng_last"], dict), "the queue is saved with the state"
    for a in levers:
        assert a["live"] and a["eng_cell"] == engage.cell(a["citizen_id"]) and a.get("owner") and a.get("username")
        if a["purpose"] == "eng_like":
            assert "like" in a["eng_cell"], a
        elif a["why"] == "first_reply":
            assert "follow" in a["eng_cell"], a
    follows = collections.Counter(a["username"] for a in levers if a["purpose"] == "eng_follow")
    assert max(follows.values(), default=0) <= config.ENG_FOLLOWS_PER_DAY
    assert {w["kind"] for w in run["world"].writes} >= {"follow"}, "the follow reached the platform"


# ---- 1. the checklist: nothing switched off ---------------------------------------------------------------------
def test_every_job_type_runs(run):
    modes = {w["kind"] for w in run["world"].writes} | {a["act"] for a in run["acts"]}
    written = {a["act"] for a in run["acts"] if a.get("act") in JOB_TYPES and a.get("post_id")}
    assert JOB_TYPES <= written, f"missing: {JOB_TYPES - written} (seen {sorted(modes)})"


def test_every_background_duty_fires(run):
    s, tmp, acts = run["spies"], run["tmp"], run["acts"]
    assert s["register"].calls and any(a["act"] == "register" for a in acts), "registration drip"
    assert s["pulse"].calls, "pulse.update"
    assert s["facts"].calls, "the fact desk's pauses (facts.refresh)"
    assert s["amp_tick"].calls, "amp.tick"
    assert s["refresh"].calls >= 2 and s["reply_backs"].calls >= 2, "targets and reply-backs are read again and again"
    assert s["own_likes"].calls and any(a["act"] == "like" and a.get("purpose") == "reply_like" for a in acts), \
        "own_likes (todo/20 step 8)"
    status = json.loads((tmp / "data" / "status.json").read_text())
    assert status["accounts"]["voices"] >= VOICES
    if run["split"]:                        # written at the start of the run (every 30 s): the writer is there first
        assert "writer" in status["threads"] and set(status["threads"]) <= {"reader", "writer", "pulse", *DRAFTER_NAMES}
        assert DRAFTER_NAMES <= set(status["threads"]), "every drafter has its own heartbeat"
        assert s["pulse"].threads == {"pulse"}, f"pulse.update only runs in the pulse thread: {s['pulse'].threads}"
        assert set(status["queue"]) == {"reply_backs", "candidates", "drafts_ready", "drafts_inflight"}
        assert {"oldest_waiting_s", "oldest_queued_s"} <= set(status)
    state = json.loads((tmp / "data" / "swan_state.json").read_text())
    assert state["targeter"]["items"] and state["replied_posts"], "save_state with the targeter's queue and funnel"
    assert (tmp / "data" / "latest_snapshot.json").exists(), "the Latest snapshot for swan-blue (todo/21 G1)"
    assert any(json.loads(line)["proc"] == "swan-bot" for line in (tmp / "logs" / "feed_reads.jsonl").read_text().splitlines())


def test_hidden_post_limit_parks_a_voice(run):
    parked = f"u{VOICES - 1}"
    assert not [w for w in run["world"].writes if w["username"] == parked and w["kind"] in ("post", "reply", "repost")]


def test_todo20_and_todo21_logging(run):
    acts = run["acts"]
    assert any(a["act"] == "requeue" and a["why"].startswith("gate:") for a in acts), "a failed draft is requeued (G8)"
    assert any(a["act"] == "skip" and a["why"] == "read" for a in acts), "the light read's skip"
    assert any(a["act"] == "refresh" and "funnel" in a for a in acts), "the funnel line (G12)"
    assert any(a["act"] == "reject" for a in acts), "rejects are logged"
    replies = [a for a in acts if a["act"] == "reply" and a.get("post_id")]
    assert replies and all("read_ok" in a and "style" in a and "target_class" in a for a in replies)


# ---- 2. the core rules -----------------------------------------------------------------------------------------
def test_only_the_writer_writes(run):
    threads = {w["thread"] for w in run["world"].writes}
    assert threads == {"MainThread"}, threads
    assert {a.get("thread") for a in run["acts"] if a["act"] in JOB_TYPES} == {"MainThread"}


def test_pacing_never_faster_and_backs_off_on_429(run):
    sends = [w for w in run["world"].writes if w["kind"] in ("post", "reply", "repost", "429")]
    gaps = [b["t"] - a["t"] for a, b in zip(sends, sends[1:])]
    assert gaps and min(gaps) >= GAP - 0.02, f"two writes {min(gaps):.3f} s apart (pace_gap {GAP})"
    hit = next(i for i, w in enumerate(sends) if w["kind"] == "429")
    assert sends[hit + 1]["t"] - sends[hit]["t"] >= RETRY_AFTER, "a 429 waits its Retry-After before the next write"


def test_voice_gaps_hold(run):
    last = {}
    for w in run["world"].writes:
        if w["kind"] not in ("post", "reply", "repost"):
            continue
        act = next((a for a in run["acts"] if a.get("post_id") == w["post_id"] and a["act"] in JOB_TYPES), None)
        mode = act["act"] if act else w["kind"]
        need = (REPLY_BACK_GAP if mode == "reply_back" else REPOST_GAP if mode in ("repost", "thread_answer")
                else VOICE_GAP)
        if w["username"] in last:
            assert w["t"] - last[w["username"]] >= need - 0.02, (w["username"], mode, w["t"] - last[w["username"]])
        last[w["username"]] = w["t"]


def test_no_double_replies(run):
    acts = [a for a in run["acts"] if a.get("post_id") and a["act"] in JOB_TYPES]
    for mode in ("reply", "reply_back", "journalist", "second_voice"):
        targets = [a["target_post"] for a in acts if a["act"] == mode]
        assert len(targets) == len(set(targets)), (mode, targets)
    first = {a["target_post"]: a["persona"] for a in acts if a["act"] == "reply"}
    assert all(first.get(a["target_post"]) != a["persona"] for a in acts if a["act"] == "second_voice")
    answered = [a["target_post"] for a in acts if a["act"] in ("reply", "reply_back")]
    assert len(answered) == len(set(answered)), "a citizen item is answered once"


def test_state_files_have_one_writer_and_are_replaced_atomically(run):
    owners = {}
    for path, thread in run["spies"]["save_json"] + run["spies"]["snapshot"]:
        owners.setdefault(path, set()).add(thread)
    assert all(len(t) == 1 for t in owners.values()), owners
    assert all(t == {"MainThread"} for p, t in owners.items() if "latest_snapshot" not in p), "the writer saves"
    if run["split"]:
        assert owners[str(run["tmp"] / "data" / "latest_snapshot.json")] == {"reader"}
    assert not list(run["tmp"].rglob("*.tmp")), "every file was written to a .tmp and replaced"


# ---- 3. the watchdog and the clean stop (split loop only) -------------------------------------------------------
def test_worker_without_a_heartbeat_is_a_problem():
    stop, beats = threading.Event(), {}
    w = bot.Worker("drafter", lambda: stop.wait(0.05), stop, beats, silent_s=10)
    w.start()
    time.sleep(0.1)
    assert w.problem() is None
    assert "no heartbeat" in w.problem(now=time.time() + 60)
    stop.set()
    w.join(1)


def test_worker_rides_out_a_transient_network_error(monkeypatch):
    """23 Oct: one SSLEOFError in the reader exited the whole bot. A blip costs the round; a real bug or an outage still
    ends the thread for the watchdog."""
    monkeypatch.setattr(bot, "NET_RETRY_S", 0)
    stop, beats, calls = threading.Event(), {}, [0]

    def step():
        calls[0] += 1
        if calls[0] < 3:
            raise bot.urllib.error.URLError(bot.ssl.SSLEOFError("UNEXPECTED_EOF_WHILE_READING"))
        if calls[0] == 5:
            stop.set()

    w = bot.Worker("reader", step, stop, beats, silent_s=10)
    w.start()
    w.join(2)
    assert w.error is None and calls[0] == 5

    def outage():
        raise ConnectionResetError("down")

    w = bot.Worker("reader", outage, threading.Event(), {}, silent_s=10)
    w.start()
    w.join(2)
    assert isinstance(w.error, ConnectionResetError) and w.net_errors == bot.NET_MAX_IN_ROW

    def bug():
        raise KeyError("x")

    w = bot.Worker("reader", bug, threading.Event(), {}, silent_s=10)
    w.start()
    w.join(2)
    assert isinstance(w.error, KeyError) and w.net_errors == 0


@pytest.mark.parametrize("thread", ["reader", "drafter"])
def test_watchdog_stops_the_bot_when_a_thread_dies(thread, tmp_path, monkeypatch, no_network):
    world, spies = setup_world(monkeypatch, tmp_path, split=True)
    calls = [0]
    if thread == "reader":
        real = targeting.Targeter.refresh

        def refresh(self, force=False):
            calls[0] += 1
            if calls[0] >= 3:
                raise RuntimeError("injected reader failure")
            return real(self, force)
        monkeypatch.setattr(targeting.Targeter, "refresh", refresh)
    else:
        real = bot.build_prompt

        def build_prompt(job, *a, **kw):
            calls[0] += 1
            if calls[0] >= 3:
                raise RuntimeError("injected drafter failure")
            return real(job, *a, **kw)
        monkeypatch.setattr(bot, "build_prompt", build_prompt)
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch, seconds=30)
    assert e.value.code == 1
    assert spies["alerts"] and thread in spies["alerts"][0] and "THREAD DIED" in spies["alerts"][0]
    died = [a for a in actions(tmp_path) if a["act"] == "thread_died"]
    assert died and died[0]["thread"].startswith(thread) and "injected" in died[0]["why"]
    state = json.loads((tmp_path / "data" / "swan_state.json").read_text())
    assert "targeter" in state, "the state is saved before the exit"


@pytest.mark.parametrize("split", [True, False], ids=["split", "serial"])
def test_dropped_connection_on_a_send_costs_one_round(split, tmp_path, monkeypatch, no_network):
    """23 Oct: only the reader and drafter threads rode out a network error; one dropped connection in the writer's
    send, like or registration still exited the bot. Now it is logged (net_error), the draft is not sent again (the
    outcome is unknown) and the bot goes on writing."""
    world, spies = setup_world(monkeypatch, tmp_path, split=split, amp_off=True)
    monkeypatch.setattr(bot, "NET_RETRY_S", 0.05)
    real, dropped = world.write, []

    def write(rec, kind, target=None, body=None):
        if kind == "reply" and not dropped:
            dropped.append(target)
            raise bot.urllib.error.URLError(bot.ssl.SSLEOFError("UNEXPECTED_EOF_WHILE_READING"))
        return real(rec, kind, target, body)

    monkeypatch.setattr(world, "write", write)
    run_main(monkeypatch, seconds=12)                          # would raise out of main() before the fix
    acts = actions(tmp_path)
    assert dropped and any(a["act"] == "net_error" and a["why"] == "URLError" for a in acts)
    assert sum(1 for w in world.writes if w["kind"] == "reply") >= 2, "the bot kept replying after the blip"


def test_no_model_pauses_the_drafter(tmp_path, monkeypatch, no_network):
    """23 Oct: with no model answering, the drafter lost 27,858 jobs in 3 h because nothing made it wait. One failed
    draft now pauses drafting for NO_MODEL_PAUSE_S: each drafter tries at most once per pause window, nothing is lost
    or requeued per attempt, and the log holds one episode, not a row per attempt."""
    world, spies = setup_world(monkeypatch, tmp_path, split=True, amp_off=True)
    attempts, lock = [], threading.Lock()

    def stub(gen, job, system, user, *a, **kw):
        with lock:
            attempts.append((time.time(), threading.current_thread().name, job["mode"]))
        job.setdefault("meta", {})
        return None, None, None

    monkeypatch.setattr(bot, "draft_checked", stub)
    monkeypatch.setattr(bot, "NO_MODEL_PAUSE_S", 5)
    run_main(monkeypatch, seconds=12)
    acts = actions(tmp_path)
    waves = math.ceil(12 / 5)       # 12 s of 5 s pauses: each of the drafters may try once per wave
    assert 1 <= len(attempts) <= config.DRAFTERS * waves, \
        f"{len(attempts)} attempts in 12 s with {config.DRAFTERS} drafters: the drafter kept spinning"
    per_thread = collections.defaultdict(list)
    for t, name, _ in attempts:
        per_thread[name].append(t)
    assert all(b - a >= 5 - 0.2 for ts in per_thread.values() for a, b in zip(ts, ts[1:])), per_thread
    assert not [a for a in acts if a["act"] in ("lost", "requeue") and str(a.get("why")).endswith("no_model")]
    rows = [a for a in acts if a["act"] == "no_model"]
    assert 1 <= len(rows) <= 3 and rows[0]["phase"] == "start" and rows[0]["n"] >= 1, rows


def test_no_model_for_minutes_alerts_once(tmp_path, monkeypatch, no_network):
    """Drafting that finds no model for NO_MODEL_ALERT_N drafts in a row is a push alert, once per episode, not a quiet
    banner (todo/34 item 5)."""
    world, spies = setup_world(monkeypatch, tmp_path, split=True, amp_off=True)
    monkeypatch.setattr(bot, "draft_checked",
                        lambda gen, job, system, user, *a, **kw: (job.setdefault("meta", {}), (None, None, None))[1])
    monkeypatch.setattr(bot, "NO_MODEL_PAUSE_S", 0.3)
    run_main(monkeypatch, seconds=12)
    said = [m for m in spies["alerts"] if "NO MODEL" in m]
    assert len(said) == 1 and not any("recovered" in m for m in spies["alerts"]), spies["alerts"]
    rows = [a for a in actions(tmp_path) if a["act"] == "no_model"]
    assert 1 <= len(rows) <= 12 / bot.NO_MODEL_LOG_EVERY_S + 3, f"{len(rows)} rows: one per attempt, not per episode"
    assert not [a for a in actions(tmp_path) if a["act"] == "lost" and a.get("why") == "no_model"]


@pytest.mark.parametrize("mode", ["reply", "reply_back", "journalist", "post", "second_voice"])
def test_no_model_defers_every_mode_and_drafting_resumes(mode, tmp_path, monkeypatch, no_network):
    """23 Oct: a journalist, post or second-voice draft that found no model was dropped (and re-picked ~200 times a
    second). Now every mode is put back untouched: at most one attempt per pause window per drafter, no lost row, and
    once a model answers again the very job that was held back is drafted and written."""
    world, spies = setup_world(monkeypatch, tmp_path, split=True, amp_off=True)
    pause, window = 1.0, 3.0
    monkeypatch.setattr(bot, "NO_MODEL_PAUSE_S", pause)
    monkeypatch.setattr(bot, "NO_MODEL_RECOVER_S", 0.2)
    failed, first, lock = [], [], threading.Lock()

    def no_model_for_mode(gen, job, system, user, recent, on_reject=None, ledger=None):
        body = (job.get("target") or {}).get("body") or ""
        if job["mode"] == mode and "LOSE-ME" not in body and "SKIP-ME" not in body:
            with lock:
                now = time.time()
                first.append(now) if not first else None
                if now - first[0] < window:          # the window opens at this mode's first draft, then a model answers
                    failed.append(dict(t=now, thread=threading.current_thread().name,
                                       target=(job.get("target") or {}).get("post_id")))
                    job.setdefault("meta", {})
                    return None, None, None
        return fake_draft_checked(gen, job, system, user, recent, on_reject, ledger)

    monkeypatch.setattr(bot, "draft_checked", no_model_for_mode)
    run_main(monkeypatch, seconds=18)
    acts = actions(tmp_path)
    assert failed, f"{mode} was never drafted: the test did not reach it"
    per_thread = collections.defaultdict(list)
    for f in failed:
        per_thread[f["thread"]].append(f["t"])
    assert all(b - a >= pause - 0.15 for ts in per_thread.values() for a, b in zip(ts, ts[1:])), per_thread
    assert len(failed) <= config.DRAFTERS * (math.ceil(window / pause) + 1), f"{len(failed)} attempts: a spin"
    assert not [a for a in acts if a["act"] in ("lost", "requeue") and str(a.get("why")).endswith("no_model")]
    rows = [a for a in acts if a["act"] == "no_model"]
    assert 1 <= len(rows) <= 6 and rows[0]["phase"] == "start" and mode in rows[0]["modes"], rows
    done = [a for a in acts if a["act"] == mode and a.get("post_id")]
    assert done, f"{mode} never completed after the model came back"
    if mode in ("reply", "journalist"):      # (a second voice may rightly be skipped later: the citizen answered us)
        assert failed[0]["target"] in {a["target_post"] for a in done}, "the job held back was not the one written"
    said = [m for m in spies["alerts"] if "NO MODEL" in m]
    assert len(said) <= 1 and bool(said) == any("recovered" in m for m in spies["alerts"]), spies["alerts"]
    ends = [r for r in rows if r["phase"] == "end"]     # (other modes answer meanwhile here, so there may be two episodes)
    assert rows[-1]["phase"] == "end" and sum(r["n"] for r in ends) == len(failed) and ends[-1]["duration_s"] >= 0, rows


@pytest.mark.parametrize("wait_says_zero", [False, True], ids=["precheck", "old_bug"])
def test_spent_allowance_and_parked_free_models_do_not_spin(wait_says_zero, tmp_path, monkeypatch, no_network):
    """The 22 Oct 19:13Z incident: today's allowance spent, the free models parked, nothing can answer. With the real
    llm.Generator: the loop sees it before drafting (one episode row, no attempts, no model called). With the wait
    forced to 0, as the old next_available_in said, drafts are tried but at most one wave per pause window, and no job
    is lost."""
    from swan_bot import llm
    real_draft_checked = bot.draft_checked
    world, spies = setup_world(monkeypatch, tmp_path, split=True, amp_off=True)
    day = dt.datetime.now(llm.BUDGET_DAY).date().isoformat()
    monkeypatch.setattr(llm, "SPEND_FILE", tmp_path / "spend.json")
    monkeypatch.setattr(llm, "USAGE_FILE", tmp_path / "usage.json")
    (tmp_path / "spend.json").write_text(json.dumps({day: 10.0}))
    for attr, val in (("LLM_BUDGET_DAYS", [(day, day, 1)]), ("LLM_BUDGET_USD", 10.0), ("LLM_DAILY_FLOOR_USD", 0.0)):
        monkeypatch.setattr(config, attr, val)
    gen = llm.Generator("unused")
    gen.chain = [("bedrock", "moonshotai.kimi-k2.5"), ("groq", "free-a"), ("groq", "free-b")]
    gen.parked = {"free-a": time.time() + 3600, "free-b": time.time() + 3600}

    def no_call(*a, **kw):
        raise AssertionError("a model was called with the allowance spent and the free models parked")

    gen._call = no_call
    assert gen.budget_left() == 0.0 and gen.no_model_wait(priority=True) > 0
    if wait_says_zero:
        gen.no_model_wait = lambda priority=False, models=None: 0.0
        gen.next_available_in = lambda *a, **kw: 0.0
    monkeypatch.setattr(bot, "Generator", lambda *a, **kw: gen)
    attempts = []
    monkeypatch.setattr(bot, "draft_checked", lambda *a, **kw: (attempts.append(time.time()),
                                                                 real_draft_checked(*a, **kw))[1])
    monkeypatch.setattr(bot, "NO_MODEL_PAUSE_S", 1.0)
    run_main(monkeypatch, seconds=8)
    acts = actions(tmp_path)
    assert not [a for a in acts if a["act"] in ("lost", "requeue") and str(a.get("why")).endswith("no_model")]
    rows = [a for a in acts if a["act"] == "no_model"]
    assert 1 <= len(rows) <= 3, f"{len(rows)} episode rows in 8 s"
    assert not [a for a in acts if a["act"] in JOB_TYPES and a.get("post_id")], "nothing could be written"
    if wait_says_zero:
        assert 1 <= len(attempts) <= config.DRAFTERS * (math.ceil(8 / 1.0) + 1), f"{len(attempts)} attempts: a spin"
    else:
        assert not attempts and rows[0]["modes"] == {"any": rows[0]["n"]} and rows[0]["wait_s"] > 0, (attempts, rows)


def test_sigterm_stops_cleanly_with_nothing_half_sent(tmp_path, monkeypatch, no_network):
    world, spies = setup_world(monkeypatch, tmp_path, split=True, amp_off=True)
    handlers = signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)
    timer = threading.Timer(3.0, lambda: os.kill(os.getpid(), signal.SIGTERM))
    timer.start()
    t0 = time.time()
    try:
        run_main(monkeypatch, seconds=60)              # returns (exit 0) long before --hours
    finally:
        timer.cancel()
    assert time.time() - t0 < 20, "SIGTERM ends the run"
    assert (signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)) == handlers, "handlers restored"
    acts = actions(tmp_path)
    logged = {a["post_id"] for a in acts if a["act"] in JOB_TYPES and a.get("post_id")}
    sent = {w["post_id"] for w in world.writes if w["kind"] in ("post", "reply", "repost")}
    assert sent and sent == logged, "every write that went out was recorded"
    state = json.loads((tmp_path / "data" / "swan_state.json").read_text())
    assert set(state["replied_posts"]) >= {a["target_post"] for a in acts if a["act"] in ("reply", "reply_back")}
    assert spies["amp_tick"].calls and not [w for w in world.writes if w["kind"] == "repost"], \
        "AMPLIFY_OFF: amp.tick still runs, the amplifier's jobs don't"
