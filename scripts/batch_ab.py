"""Read-only A/B: are batched drafts as good as one-draft-per-call? Posts nothing.

    python scripts/batch_ab.py --freeze              # save ~60 real jobs (live targets, 2 feed reads) to data/ab/jobs.json
    python scripts/batch_ab.py                       # draft them single / batch-4 / batch-6, judge, print the table
    python scripts/batch_ab.py --arms single,batch-4 --judge gemini-3.5-flash-lite

Every arm drafts the same frozen jobs with the same model. Metrics per arm (first try, no redraft):
gate pass rate and reject reasons, mix-ups and persona bleed, pass rate by position in the batch, diversity
(mean 5-word-shingle overlap, distinct openings), hedging, own-persona detail, and a blind pairwise judge
(single vs batched, same job, both orders, a split verdict is a tie) on two questions: which is better, and
which is sharper (commits to its point rather than drifting to bland middle-ground wording).
Writes data/ab/run-<time>.json (every draft) and data/ab/blind-<time>.md (20 pairs for a human read, key at the end).
LLM calls: one per job for single, one per 4-6 jobs batched, two per judged pair.
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import itertools
import json
import math
import pathlib
import random
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import capturethenarrative as ctn  # noqa: E402
from swan_bot import batch, config, content, quality  # noqa: E402
from swan_bot.bot import build_prompt  # noqa: E402
from swan_bot.llm import Generator  # noqa: E402
from swan_bot.targeting import Targeter  # noqa: E402

AB = config.DATA / "ab"
JOBS = AB / "jobs.json"
HEDGE = re.compile(r"\b(maybe|perhaps|might be|i'?m not sure|not sure|both sides|fair enough|to be fair|i can see why|"
                   r"i get why|it'?s complicated|could be wrong|who knows|not saying|i suppose|kind of|sort of|"
                   r"on the other hand|either way is fine|up to you)\b", re.I)

JUDGE_SYSTEM = (
    "You judge drafts for a referendum campaign game set in Kingstonia, a fictional Pacific island nation. Both "
    "drafts argue for a No vote on a vaccination-certificate rule and are written as the same named local person. "
    "Answer two questions.\n"
    "better: which draft would work better on the platform? Weigh, in order: (1) for a reply, does it answer the "
    "neighbour's actual point (for a post: does it make one clear point); (2) one concrete, specific detail rather "
    "than general statements; (3) does it sound like a real local person, not a slogan or an AI; (4) would it move "
    "an undecided reader toward No without putting them off.\n"
    "sharper: which draft has more conviction and edge: a clear, committed, memorable point, as opposed to hedged, "
    "bland, cautious or generic middle-of-the-road wording.\n"
    "Do not reward length. Do not reward invented facts. If the two are genuinely equal on a question, say tie.\n"
    'Answer JSON only: {"reason": "<one short sentence>", "better": "1" or "2" or "tie", "sharper": "1" or "2" or "tie"}'
)


def wilson(k, n, z=1.96):
    """95% interval for a proportion k/n."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


# ---- freeze ---------------------------------------------------------------------------------
def freeze(n_reply, n_second, n_post, seed):
    rng = random.Random(seed)
    social = ctn.LegitSocial(max_retries=2)
    targeter = Targeter(social, log=lambda r: None)
    targeter.refresh(force=True)
    cands, authors = [], set()
    while len(cands) < n_reply + n_second:
        c = targeter.next_target(set(), set(), {})
        if not c:
            break
        if c["post"]["author_id"] not in authors:
            authors.add(c["post"]["author_id"])
            cands.append(c)
    personas = [p["key"] for p in content.PERSONAS]
    jobs = []

    def add(mode, frame, cand=None):
        """Persona that fits the frame, never repeated inside a block of 12 jobs of one mode (so any batch of
        4 or 6 has different people, as in the bot)."""
        same = [j for j in jobs if j["mode"] == mode]
        block = {j["rec"]["persona"] for j in same[len(same) // 12 * 12:]}
        free = [k for k in personas if k not in block]
        fit = [k for k in free if frame in content.PERSONA_BY_KEY[k]["frames"]]
        key = rng.choice(fit or free)
        frame = frame or content.pick_frame(content.PERSONA_BY_KEY[key])
        job = dict(mode=mode, frame=frame, rec={"persona": key})
        if cand:
            job.update(target=cand["post"], wants=cand["wants"], context=cand["context"])
        jobs.append(job)

    for c in cands[:n_reply]:
        add("reply", c["frame"], c)
    for c in cands[n_reply:n_reply + n_second] or cands[:n_second]:
        second = content.FRAMES[c["frame"]]["second"]
        add("second_voice", rng.choice(second) if isinstance(second, list) else second, c)
    for _ in range(n_post):
        add("post", None)
    for i, j in enumerate(jobs):
        j["id"] = i
    AB.mkdir(parents=True, exist_ok=True)
    JOBS.write_text(json.dumps(dict(frozen=dt.datetime.now(dt.timezone.utc).isoformat(), seed=seed,
                                    headline=targeter.headline, jobs=jobs), indent=1))
    by = {m: sum(j["mode"] == m for j in jobs) for m in batch.MODES}
    print(f"froze {len(jobs)} jobs {by} to {JOBS}")


# ---- drafting -------------------------------------------------------------------------------
def call_until(fn, gen, model, tries=12):
    """fn() -> result or None while the model is parked (rate limit): wait it out, a few times at most."""
    for _ in range(tries):
        out = fn()
        if out is not None:
            return out
        wait = max(5.0, gen.parked.get(model, 0) - time.time())
        print(f"  {model} unavailable; waiting {wait:.0f} s")
        time.sleep(min(wait, 120))
    raise SystemExit(f"{model} stayed unavailable; stopping (results so far are not saved)")


def run_single(jobs, gen, model, headline, rng):
    class T:                                       # build_prompt only needs .headline
        pass
    t = T()
    t.headline = headline
    out, accepted = [], []
    for job in jobs:
        random.seed(rng.random())                  # build_prompt picks shape/opener with the global RNG
        persona, system, user = build_prompt(job, t)
        raw, backend = call_until(lambda: (lambda r: r if r[0] is not None else None)(gen.complete(system, user, models={model})),
                                  gen, model)
        body = (job.get("target") or {}).get("body") or ""
        text, why = quality.check(raw, job["mode"], accepted, prompt_text=user, target_text=body,
                                  wants=job.get("wants") or ())
        if text:
            accepted.append(text)
        out.append(dict(id=job["id"], mode=job["mode"], persona=job["rec"]["persona"], text=text, why=why, raw=raw,
                        backend=backend, batch_pos=None, batch_size=1, finish=gen.last_finish))
        print(f"  single #{job['id']:>2} {job['mode']:12} {'ok' if text else why}")
    return out


def run_batch(jobs, gen, model, headline, size, rng, reasoning=None):
    drafter = batch.Drafter(gen, size=size, reasoning=reasoning)
    out, accepted = [], []
    for mode in batch.MODES:
        group = [j for j in jobs if j["mode"] == mode]
        for i in range(0, len(group), size):
            chunk = group[i:i + size]
            res = call_until(lambda: drafter.draft(chunk, accepted, headline=headline, models={model}, rng=rng),
                             gen, model)
            for r in res:
                if r["text"]:
                    accepted.append(r["text"])
                out.append(dict(id=r["job"]["id"], mode=mode, persona=r["job"]["rec"]["persona"], text=r["text"],
                                why=r["why"], raw=r["raw"], backend=r["backend"], batch_pos=r["batch_pos"],
                                batch_size=r["batch_size"], batch_id=r["batch_id"], finish=r["finish"],
                                their_point=r["their_point"]))
            print(f"  batch-{size} {mode:12} {len(chunk)} jobs: "
                  f"{sum(bool(r['text']) for r in res)} ok {[r['why'] for r in res if not r['text']]}")
    return sorted(out, key=lambda r: r["id"])


# ---- judge ----------------------------------------------------------------------------------
def judge_prompt(job, a, b):
    persona = content.PERSONA_BY_KEY[job["rec"]["persona"]]
    who = f"Written as {persona['name']}, who {persona['role']} in {persona['place']} (voice: {persona['voice']})."
    if job["mode"] == "post":
        task = "Task: a new post saying why they're voting No."
    else:
        task = f"Task: a reply to this neighbour, who hasn't fully decided:\n<<<{job['target']['body'][:600]}>>>"
    return f"{who}\n{task}\n\nDraft 1:\n<<<{a}>>>\n\nDraft 2:\n<<<{b}>>>"


def parse_verdict(raw):
    try:
        d = json.loads(re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.M))
        return {k: str(d.get(k, "tie")).strip().lower() for k in ("better", "sharper")}, d.get("reason", "")
    except (json.JSONDecodeError, AttributeError):
        return None, raw


def judge_pairs(pairs, gen, model, workers):
    """pairs: [(job, single_text, batched_text)] -> list of dicts with score_better/score_sharper for *batched*
    (1 win, 0.5 tie or split, 0 loss), from two calls with the order swapped."""

    def one(job, s, b):
        verdicts = []
        for first, second, batched_is in ((s, b, "2"), (b, s, "1")):
            for _ in range(2):                     # one re-ask if the JSON is unusable
                raw, _ = call_until(lambda: (lambda r: r if r[0] is not None else None)(
                    gen.complete(JUDGE_SYSTEM, judge_prompt(job, first, second), json_mode=True, models={model},
                                 reasoning="low")), gen, model)
                v, reason = parse_verdict(raw)
                if v:
                    break
            v = v or {"better": "tie", "sharper": "tie"}
            verdicts.append({k: 1.0 if x == batched_is else 0.5 if x == "tie" else 0.0 for k, x in v.items()} |
                            {"reason": reason})
        res = {"id": job["id"], "mode": job["mode"]}
        for k in ("better", "sharper"):
            x, y = verdicts[0][k], verdicts[1][k]
            res[k] = x if x == y else 0.5                 # orders disagree: position bias, call it a tie
            res[k + "_consistent"] = x == y
        res["reasons"] = [v["reason"] for v in verdicts]
        return res

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(lambda p: one(*p), pairs))


# ---- metrics --------------------------------------------------------------------------------
def opening(t):
    return " ".join(re.findall(r"[a-z']+", t.lower())[:4])


def own_detail(text, key):
    return bool(batch._words(text) & batch.DISTINCT[key])


def arm_metrics(rows):
    n = len(rows)
    ok = [r for r in rows if r["text"]]
    texts = [r["text"] for r in ok]
    sims = [quality.similar(a["text"], b["text"]) for a, b in itertools.combinations(ok, 2) if a["mode"] == b["mode"]]
    reasons = {}
    for r in rows:
        if not r["text"]:
            reasons[r["why"]] = reasons.get(r["why"], 0) + 1
    by_pos = {}
    for r in rows:
        if r["batch_pos"] is not None:
            by_pos.setdefault(r["batch_pos"], []).append(bool(r["text"]))
    return dict(
        n=n, passed=len(ok), pass_rate=len(ok) / n if n else 0, pass_ci=wilson(len(ok), n),
        by_mode={m: f"{sum(bool(r['text']) for r in rows if r['mode'] == m)}/{sum(r['mode'] == m for r in rows)}"
                 for m in batch.MODES},
        rejects=dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
        mean_overlap=sum(sims) / len(sims) if sims else 0,
        distinct_openings=len({opening(t) for t in texts}) / len(texts) if texts else 0,
        hedge_rate=sum(bool(HEDGE.search(t)) for t in texts) / len(texts) if texts else 0,
        own_detail=sum(own_detail(r["text"], r["persona"]) for r in ok) / len(ok) if ok else 0,
        mean_chars=sum(map(len, texts)) / len(texts) if texts else 0,
        by_pos={p: f"{sum(v)}/{len(v)}" for p, v in sorted(by_pos.items())},
        pos_rates={p: sum(v) / len(v) for p, v in sorted(by_pos.items())},
        cut_off=sum(r.get("finish") == "length" for r in rows),
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--freeze", action="store_true", help="read live targets and save a new job set")
    ap.add_argument("--replies", type=int, default=30)
    ap.add_argument("--second", type=int, default=12)
    ap.add_argument("--posts", type=int, default=18)
    ap.add_argument("--arms", default="single,batch-4,batch-6", help="single, batch-N, batch-N-low (reasoning low)")
    ap.add_argument("--model", default="gemini-3.5-flash-lite", help="drafting model (all arms)")
    ap.add_argument("--judge", default="openai/gpt-oss-120b", help="judge model ('' to skip judging)")
    ap.add_argument("--workers", type=int, default=3, help="parallel judge calls")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--reuse-single", metavar="RUN_JSON", help="take the single arm from an earlier run (same jobs)")
    args = ap.parse_args()
    config.load_env()
    if args.freeze:
        freeze(args.replies, args.second, args.posts, args.seed)
        return
    frozen = json.loads(JOBS.read_text())
    jobs, headline = frozen["jobs"], frozen["headline"]
    gen = Generator(config.team_code())
    rng = random.Random(args.seed)
    t0 = time.time()
    runs = {}
    for arm in args.arms.split(","):
        print(f"== {arm}")
        if arm == "single" and args.reuse_single:
            runs[arm] = json.loads(pathlib.Path(args.reuse_single).read_text())["runs"]["single"]
        elif arm == "single":
            runs[arm] = run_single(jobs, gen, args.model, headline, rng)
        else:
            parts = arm.split("-")
            runs[arm] = run_batch(jobs, gen, args.model, headline, int(parts[1]), rng,
                                  reasoning=parts[2] if len(parts) > 2 else None)
    metrics = {arm: arm_metrics(rows) for arm, rows in runs.items()}
    by_id = {j["id"]: j for j in jobs}
    judged = {}
    if args.judge and "single" in runs:
        single = {r["id"]: r["text"] for r in runs["single"]}
        for arm, rows in runs.items():
            if arm == "single":
                continue
            pairs = [(by_id[r["id"]], single[r["id"]], r["text"]) for r in rows if r["text"] and single.get(r["id"])]
            print(f"== judging single vs {arm}: {len(pairs)} pairs x 2 orders on {args.judge}")
            judged[arm] = judge_pairs(pairs, gen, args.judge, args.workers)

    # ---- report ----
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    base = metrics.get("single")
    print(f"\n{len(jobs)} jobs, model {args.model}, judge {args.judge or '-'}, {time.time() - t0:.0f} s, "
          f"LLM calls {gen.calls}\n")
    head = ["metric"] + list(runs)
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]

    def row(name, f):
        lines.append("| " + " | ".join([name] + [f(arm) for arm in runs]) + " |")

    row("LLM calls (drafting)", lambda a: str(len({r.get("batch_id") or r["id"] for r in runs[a]})))
    row("gate pass (first try)", lambda a: f"{metrics[a]['passed']}/{metrics[a]['n']} = {metrics[a]['pass_rate']:.0%} "
        f"[{metrics[a]['pass_ci'][0]:.0%}-{metrics[a]['pass_ci'][1]:.0%}]")
    row("  vs single", lambda a: f"{metrics[a]['pass_rate'] / base['pass_rate']:.0%}" if base and base["pass_rate"] else "-")
    row("  by mode (post / reply / 2nd)", lambda a: " / ".join(metrics[a]["by_mode"][m] for m in batch.MODES))
    row("top rejects", lambda a: ", ".join(f"{k} {v}" for k, v in list(metrics[a]["rejects"].items())[:4]) or "-")
    row("pass by position", lambda a: " ".join(f"{p + 1}:{v}" for p, v in metrics[a]["by_pos"].items()) or "-")
    row("mean overlap (lower = more varied)", lambda a: f"{metrics[a]['mean_overlap']:.3f}")
    row("distinct openings", lambda a: f"{metrics[a]['distinct_openings']:.0%}")
    row("hedging drafts", lambda a: f"{metrics[a]['hedge_rate']:.0%}")
    row("uses own persona detail", lambda a: f"{metrics[a]['own_detail']:.0%}")
    row("mean length (chars)", lambda a: f"{metrics[a]['mean_chars']:.0f}")
    row("cut-off answers", lambda a: str(metrics[a]["cut_off"]))
    verdicts = {}
    for arm, res in judged.items():
        n = len(res)
        for k in ("better", "sharper"):
            s = sum(r[k] for r in res)
            wins, ties = sum(r[k] == 1.0 for r in res), sum(r[k] == 0.5 for r in res)
            verdicts[(arm, k)] = (s / n if n else 0, wilson(s, n), wins, ties, n - wins - ties,
                                  sum(r[k + "_consistent"] for r in res) / n if n else 0)
    for k in ("better", "sharper"):
        row(f"judge '{k}': batched win rate", lambda a: "-" if (a, k) not in verdicts else
            f"{verdicts[(a, k)][0]:.0%} [{verdicts[(a, k)][1][0]:.0%}-{verdicts[(a, k)][1][1]:.0%}] "
            f"(W{verdicts[(a, k)][2]}/T{verdicts[(a, k)][3]}/L{verdicts[(a, k)][4]})")
    row("judge order-consistent", lambda a: "-" if (a, "better") not in verdicts else
        f"{verdicts[(a, 'better')][5]:.0%}")

    def bar(a):
        if a == "single" or not base:
            return "baseline"
        m = metrics[a]
        checks = [m["pass_rate"] >= 0.95 * base["pass_rate"],
                  m["hedge_rate"] <= base["hedge_rate"] + 0.05,
                  not m["pos_rates"] or min(m["pos_rates"].values()) >= m["pos_rates"][0] - 0.10]
        if (a, "better") in verdicts:
            checks += [verdicts[(a, "better")][0] >= 0.45, verdicts[(a, "sharper")][0] >= 0.45]
        return "PASS" if all(checks) else "fail"
    row("**pass bar**", bar)
    table = "\n".join(lines)
    print(table)

    AB.mkdir(parents=True, exist_ok=True)
    out = AB / f"run-{stamp}.json"
    out.write_text(json.dumps(dict(args=vars(args), frozen=frozen["frozen"], metrics=metrics, judged=judged,
                                   runs=runs, table=table), indent=1, default=str))
    # blind pairs for a human read: 20 random jobs, single vs the biggest batched arm, order hidden
    big = [a for a in runs if a != "single"]
    if big and "single" in runs:
        arm = big[-1]
        single = {r["id"]: r["text"] for r in runs["single"]}
        both = [r for r in runs[arm] if r["text"] and single.get(r["id"])]
        pick = random.Random(args.seed).sample(both, k=min(20, len(both)))
        doc, key = [f"# Blind pairs: which draft is better? ({stamp})\n"], []
        for i, r in enumerate(pick, 1):
            job = by_id[r["id"]]
            flip = random.Random(args.seed + i).random() < 0.5
            a, b = (r["text"], single[r["id"]]) if flip else (single[r["id"]], r["text"])
            key.append(f"{i}: batched = {'A' if flip else 'B'}")
            who = content.PERSONA_BY_KEY[job["rec"]["persona"]]["name"]
            tgt = f"\n> citizen: {job['target']['body'][:300]}" if job.get("target") else ""
            doc.append(f"## {i}. {job['mode']} as {who}{tgt}\n\n**A:** {a}\n\n**B:** {b}\n")
        doc.append("\n---\n\nKey (don't peek):\n\n" + "\n".join(f"- {k}" for k in key))
        (AB / f"blind-{stamp}.md").write_text("\n".join(doc))
    print(f"\nsaved {out}" + (f" and {AB / f'blind-{stamp}.md'}" if big else ""))


if __name__ == "__main__":
    main()
