"""Replay eval: judge a prompt or gate change on a fixed set of real citizen comments. Posts nothing.

    python scripts/replay_eval.py freeze --n 80 --hours 48       # save real reply jobs from logs/swan_actions.jsonl
    python scripts/replay_eval.py run --tag base                 # draft them through the bot's own prompt and gate
    python scripts/replay_eval.py run --tag after                # ... again after a change (git checkout / stash)
    python scripts/replay_eval.py compare base after             # the table: motifs, concessions, asks answered, clash
    python scripts/replay_eval.py score base                     # one run's numbers

The jobs come from the log, so there is no platform call at all: the citizen's comment, its thread context, the voice's
persona and the frame/wants the current keyword rules give. The window of recent texts starts as the account's real last
100 and grows with each accepted draft, so repeats across the run show up as they would on the profile. LLM calls go to our
own providers (config.REPLY_MODELS) and are for reading and counting only; nothing drafted here is posted or aimed at
anyone. Run it on a COPY of the repo on the box (the Generator writes data/llm_spend.json and data/llm_parks.json, which the
live bot also writes): see docs/04-technical/swan-bot-runbook.md, "Replay eval". src/swan_bot/replay.py has the metrics.
"""
import argparse
import collections
import json
import pathlib
import random
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import config, content, quality, replay, targeting  # noqa: E402

OUT = config.DATA / "replay"
JOBS = OUT / "jobs.json"


def freeze(args):
    import datetime as dt
    rows = [json.loads(line) for line in open(config.LOGS / "swan_actions.jsonl") if line.strip()]
    cut = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=args.hours)
    ok = [r for r in rows if r.get("act") == "reply" and r.get("target_text") and r.get("persona") in content.PERSONA_BY_KEY
          and dt.datetime.fromisoformat(r["ts"]) >= cut]
    citizen = [r["text"] for r in rows if r.get("act") in ("reply", "second_voice", "reply_back") and r.get("text")]
    random.Random(args.seed).shuffle(ok)
    seen, jobs = set(), []
    for r in ok:
        if r["target_text"] in seen:
            continue
        seen.add(r["target_text"])
        jobs.append({k: r.get(k) for k in ("post_id", "persona", "target_text", "context", "source", "group")})
        if len(jobs) >= args.n:
            break
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump({"jobs": jobs, "window": citizen[-quality.PHRASE_WINDOW:], "frozen": time.strftime("%F %T")},
              open(JOBS, "w"), indent=1)
    print(f"froze {len(jobs)} jobs, window of {min(len(citizen), quality.PHRASE_WINDOW)} real texts -> {JOBS}")


def run(args):
    from swan_bot.bot import build_prompt, draft_checked
    from swan_bot.llm import Generator
    config.load_env()
    gen = Generator(config.team_code())
    data = json.load(open(JOBS))
    window = list(data["window"])
    done, rejects, t0 = [], collections.Counter(), time.time()
    for k, j in enumerate(data["jobs"][:args.limit] if args.limit else data["jobs"]):
        text = j["target_text"]
        frame, wants = targeting.classify(text)
        frame = frame or "F14_no_yes_but"
        job = dict(mode="reply", rec={"persona": j["persona"], "username": "replay"}, frame=frame, wants=wants,
                   target={"post_id": str(j["post_id"]), "author_id": 10 ** 6, "body": text}, context=j.get("context"),
                   source=j.get("source"), group=j.get("group"), target_class=targeting.target_class(text, j.get("context")))
        job["phrase_texts"] = window[-quality.PHRASE_WINDOW:]
        _, system, user = build_prompt(job, None, (), None, recent_texts=window)
        local = collections.Counter()

        def on_reject(why, raw, backend, repair):
            local[why.split("_")[0] if why.startswith(("phrase", "repeat", "unapproved")) else why] += 1

        reply, backend, _ = draft_checked(gen, job, system, user, window[-300:], on_reject, None)
        rejects.update(local)
        meta = job.get("meta") or {}
        if reply:
            window.append(reply)
        done.append({"post_id": j["post_id"], "target_text": text, "reply": reply, "backend": backend,
                     "frame": meta.get("read_frame") or job["frame"], "target_class": job["target_class"],
                     "rejected": dict(local), "llm_calls": meta.get("llm_calls")})
        print(f"{k + 1:3} {backend and backend[:8]!s:8} {(reply or 'LOST')[:110]!r}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    s = replay.score(done, data["window"])
    json.dump({"tag": args.tag, "git": _git(), "items": done, "score": s, "rejects": dict(rejects),
               "seconds": round(time.time() - t0)}, open(OUT / f"run-{args.tag}.json", "w"), indent=1)
    lost = sum(1 for d in done if not d["reply"])
    print(f"\n{len(done)} jobs, {lost} lost, rejects {dict(rejects.most_common(6))}, calls "
          f"{sum(d['llm_calls'] or 0 for d in done)}, spend (all days in this copy) ${sum(gen.spent().values()):.3f}")
    print(_show(s))


def _git():
    import subprocess
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                          cwd=pathlib.Path(__file__).resolve().parents[1]).stdout.strip()


def _show(s):
    return "\n".join(f"{k:22}{v:.2f}" if isinstance(v, float) else f"{k:22}{v}" for k, v in s.items())


def load(tag):
    return json.load(open(OUT / f"run-{tag}.json"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze")
    f.add_argument("--n", type=int, default=80)
    f.add_argument("--hours", type=float, default=48)
    f.add_argument("--seed", type=int, default=1)
    r = sub.add_parser("run")
    r.add_argument("--tag", required=True)
    r.add_argument("--limit", type=int, default=0)
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    s = sub.add_parser("score")
    s.add_argument("tag")
    args = ap.parse_args()
    if args.cmd == "freeze":
        freeze(args)
    elif args.cmd == "run":
        run(args)
    elif args.cmd == "compare":
        a, b = load(args.a), load(args.b)
        print(f"{args.a}: {a['git']}  {args.b}: {b['git']}")
        print(replay.compare(a["score"], b["score"], (args.a, args.b)))
    else:
        print(_show(load(args.tag)["score"]))


if __name__ == "__main__":
    main()
