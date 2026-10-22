"""One lab trial: draft the reply a strategy asks for (today's live prompt plus the strategy's instruction, on the live
reply models), show it to the stand-in citizen, classify the move. The loop runs the queue forever (swan-lab.service).

A trial costs 2 stand-in calls (the session, the classifier) on CompetitorLLM; the reply draft is content, drafted on
our usual models (CLAUDE.md rule 2). Nothing here writes to Legit Social.
"""
import collections
import concurrent.futures
import datetime as dt
import json
import random
import re
import threading
import time
import types

import capturethenarrative as ctn

from swan_bot import bot, config, content, quality
from swan_bot.llm import Generator
from swan_bot.targeting import REFERENDUM
from . import library, npc

NEWS_EVERY_S = 30 * 60
MAX_ERRORS = 3                       # a trial that fails this often is left out (no retry loop that hammers)


class News:
    """Recent in-world articles on the vote (title, summary, absolute URL), refreshed every 30 min."""

    def __init__(self):
        self.sites, self.items, self.at = ctn.NewsSites(), [], 0.0

    def heads(self):
        if time.time() - self.at > NEWS_EVERY_S:
            try:
                items = self.sites.latest(40)
            except Exception as e:                      # noqa: BLE001 (any read failure: keep the old list)
                print(f"lab: news read failed: {e}")
                items = None
            if items is not None:
                self.items = [dict(title=a["title"], summary=a.get("summary") or "", site=a["site"]["name"],
                                   url=ctn.DEFAULT_NEWS_SITES_URL + a["url"]) for a in items
                              if REFERENDUM.search(f"{a['title']} {a.get('summary') or ''}")][:8]
                self.at = time.time()
        return self.items


class Capture:
    """The generator, keeping each raw answer (the article number sits in the JSON the gate never returns)."""

    def __init__(self, gen):
        self.gen, self.raws = gen, []

    def __getattr__(self, name):
        return getattr(self.gen, name)

    def complete(self, *a, **kw):
        raw, backend = self.gen.complete(*a, **kw)
        self.raws.append(raw)
        return raw, backend


def voice_for(card, seed):
    """The same voice for a persona and seed across strategies, so strategies differ only in what they ask."""
    return random.Random(f"{card['id']}:{seed}:voice").choice(content.PERSONAS)


def news_block(heads):
    rows = "\n".join(f"{i}. {h['site']}: \"{h['title']}\" ({h['summary']})" for i, h in enumerate(heads, 1))
    return (f"\n\nRecent articles in the papers:\n{rows}\nPick the one article that best supports a No vote for THIS "
            "citizen's concern, and add \"article\": <its number> to your JSON (0 if none fits). Tie your reply to it in "
            "one line, naming the paper. Do not write any link: it is added after your text.")


def draft(strategy, card, seed, gen, news):
    """(text, backend, meta) for this strategy's reply, or (None, backend, meta) with meta["skip"] saying why."""
    persona = voice_for(card, seed)
    job = dict(mode="reply", rec=dict(persona=persona["key"]), frame=None, arm=None, wants=[], context=None,
               target=dict(post_id=card.get("target_post"), author_id=card["author_id"], body=card["target_text"]))
    config.REPLY_STYLES = [strategy["style"]]
    _, system, user = bot.build_prompt(job, types.SimpleNamespace(headline=None))
    heads = news.heads() if strategy.get("insert") == "link" else []
    if strategy["instruction"]:
        user += f"\n\nFor this reply, also: {strategy['instruction']}"
    if strategy.get("insert") == "mention":
        user += "\nDo not write their @handle: it is added before your text."
    if heads:
        user += news_block(heads)
    meta = dict(voice=persona["key"], style=strategy["style"])
    gen = Capture(gen)
    if strategy["gate"]:
        text, backend, repair = bot.draft_checked(gen, job, system, user, [])
        meta.update({k: job["meta"].get(k) for k in ("llm_calls", "repairs", "last_reject", "read_stance")},
                    repair=repair)
        if job.get("read_skip"):
            return None, backend, dict(meta, skip=f"read:{job['read_skip'][:80]}")
        if not text:
            return None, backend, dict(meta, skip=f"gate:{job['meta'].get('last_reject')}")
    else:                                               # one draft, safety checks only (e.g. overclaim)
        models, _ = bot.draft_models(job, gen)
        raw, backend = bot.complete_in_order(gen, system, user, models, max_tokens=bot.MAX_TOKENS, temperature=0.7)
        if raw is None:
            return None, None, dict(meta, skip="no_model")
        read = content.parse_read(raw)
        text = (read["reply"] or "").strip()
        meta["read_stance"] = read["stance"]
        unsafe = safety(text)
        if read["skip"] or not text or unsafe:
            return None, backend, dict(meta, skip=read["skip"] and f"read:{read['skip'][:80]}" or unsafe or "empty")
    if heads:                                           # the article the model picked, as a verified URL
        m = re.search(r'"article"\s*:\s*(\d+)', next((r for r in gen.raws if r), ""))
        pick = int(m.group(1)) if m else 0
        if 1 <= pick <= len(heads):
            h = heads[pick - 1]
            text, meta["article"] = f"{text} {h['url']}", h
    if strategy.get("insert") == "mention" and card.get("handle"):
        text = f"@{card['handle']} {text}"
    return text, backend, meta


def safety(text):
    """The checks no strategy may skip: forbidden content, voting logistics, vaccine advocacy. None when safe."""
    if quality.FORBIDDEN.search(text):
        return "forbidden_content"
    if quality.WRONG_LOGISTICS.search(text):
        return "wrong_logistics"
    if content.advocacy(text):
        return "vaccine_advocacy"
    return None


def run_trial(strategy, card, seed, gen, stand_in, news):
    rec = dict(ts=dt.datetime.now(dt.timezone.utc).isoformat(), strategy=strategy["name"],
               version=strategy["version"], persona=card["id"], stance_class=card.get("stance_class"),
               certainty=card.get("certainty"), concerns=card.get("concerns"), seed=seed, lab_model=stand_in.model)
    calls0 = stand_in.thread_calls
    if strategy["npc_reads"] == "control":
        v = voice_for(card, seed)
        text = strategy.get("control_text") or "Lovely calm morning on the harbour, the ferries are all on time."
        reads, rec["voice"] = npc.reads_post(v["name"], v["handle"], text), v["key"]
    else:
        text, backend, meta = draft(strategy, card, seed, gen, news)
        rec.update(meta, backend=backend)
        if not text:
            rec["verdict"] = None
            return rec
        v = content.PERSONA_BY_KEY[meta["voice"]]
        card_text = meta.get("article") and f"{meta['article']['site']}: {meta['article']['title']}. " \
                                            f"{meta['article']['summary']}"
        reads = npc.reads_reply(v["name"], v["handle"], text, card_text)
    rec["reply"] = text
    base = baseline_for(stand_in, card, seed)
    after, vaccine_line, _ = npc.session(stand_in, card, reads, seed)
    score, raw = npc.rate(stand_in, after)
    rec.update(after=after, vaccine_line=vaccine_line, before_view=base["view"], before=base["score"], after_score=score,
               rating_raw=raw, verdict=npc.verdict(base["score"], score), instrument=npc.INSTRUMENT,
               npc_calls=stand_in.thread_calls - calls0)
    return rec


_BASE_LOCKS, _BASE_GUARD = collections.defaultdict(threading.Lock), threading.Lock()


def baseline_for(stand_in, card, seed):
    """The card's baseline on this stand-in model and seed: from data/lab/baselines.jsonl, else made and stored.
    One lock per key, so parallel trials of the same card and seed make it once."""
    key = (card["id"], stand_in.model, seed, npc.INSTRUMENT)
    with _BASE_GUARD:
        lock = _BASE_LOCKS[key]
    with lock:
        for b in library.baselines():
            if (b["persona"], b["lab_model"], b["seed"], b.get("instrument")) == key:
                return b
        b = dict(npc.baseline(stand_in, card), persona=card["id"], lab_model=stand_in.model, seed=seed,
                 instrument=npc.INSTRUMENT, ts=dt.datetime.now(dt.timezone.utc).isoformat())
        library.record(b, "baselines.jsonl")
        return b


def write_status(name="status.json", **kw):
    config.LAB_DIR.mkdir(parents=True, exist_ok=True)
    (config.LAB_DIR / name).write_text(json.dumps(dict(ts=dt.datetime.now(dt.timezone.utc).isoformat(), **kw)))


def attempt(s, c, seed, gen, stand_in, news):
    """One queued trial, recorded the moment it finishes: ("ok", rec), ("switched", None), ("down", why) or
    ("error", why). Runs in a worker thread."""
    try:
        rec = run_trial(s, c, seed, gen, stand_in, news)
    except npc.Switched:                                # the primary went down: run again on the fallback
        return "switched", None
    except RuntimeError as e:                           # the stand-in is down (an outage, not this trial)
        return "down", str(e)
    except Exception as e:                              # noqa: BLE001 (this trial's own failure: counted, then left out)
        return "error", f"{type(e).__name__}: {e}"
    library.record(rec)
    print(f"lab: {s['name']:<20} {c['id']:<7} {c.get('stance_class') or '-':<10} seed {seed}: "
          f"{rec.get('verdict') or rec.get('skip')}")
    return "ok", rec


def loop(once=False, limit=None, model=None, local_model=None, fallback=True):
    """Run the queue (new strategy files and cards are picked up each round); wait when it is empty. Trials run
    config.LAB_CONCURRENCY at a time for the stand-in's kind (remote: several; local and competitor: one). A second
    pool (another model, e.g. local beside remote) runs as its own process: one result set, lab_model on each trial,
    its own status file."""
    config.SWITCHBACK = []                              # the lab drafts today's base behaviour, not a live arm
    gen, news = Generator(config.team_code()), News()
    stand_in = npc.StandIn(model, local_model=local_model, fallback=fallback)
    workers = config.LAB_CONCURRENCY.get(stand_in.primary.kind, 1)
    status_file = "status.json" if model is None and local_model is None else \
        f"status-{stand_in.primary.name.replace(':', '-')}.json"

    def status(**kw):
        write_status(status_file, **kw)

    errors, ran, down = {}, 0, False
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        while True:
            rows = library.trials()
            done = library.done_keys(rows, stand_in.model)
            q = [x for x in library.queue(library.strategies(), library.personas(), done)
                 if errors.get((x[0]["name"], x[1]["id"], x[2]), 0) < MAX_ERRORS]
            status(queued=len(q), trials=len(rows), ran=ran, lab_model=stand_in.model, workers=workers)
            if not q or (limit and ran >= limit):
                if once or (limit and ran >= limit):
                    return ran
                time.sleep(300)
                continue
            stand_in.restore()
            if down and not stand_in.up():              # still down: no reply drafted for nothing
                time.sleep(300)
                continue
            down = False
            batch = q[:workers * 2] if not limit else q[:min(workers * 2, limit - ran)]
            outcomes = list(pool.map(lambda x: attempt(*x, gen, stand_in, news), batch))
            for (s, c, seed), (kind, why) in zip(batch, outcomes):
                if kind == "ok":
                    ran += 1
                elif kind == "error":
                    errors[(s["name"], c["id"], seed)] = errors.get((s["name"], c["id"], seed), 0) + 1
                    print(f"lab: {s['name']} {c['id']} seed {seed} failed: {why}")
                elif kind == "down":
                    down = True
            if down:
                why = next(w for k, w in outcomes if k == "down")
                print(f"lab: {why}; waiting 5 min")
                status(queued=len(q), trials=len(rows), ran=ran, lab_model=stand_in.model, down=why)
                time.sleep(300)
