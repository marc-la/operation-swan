"""Read-only: send the same batch of real drafting jobs to each model in the chain and compare.

    python scripts/llm_compare.py                 # 4 replies + 2 posts, every model in the chain
    python scripts/llm_compare.py -n 6 --models gemini-3.5-flash,openai/gpt-oss-120b
Prints each model's drafts with the quality-gate verdict, time taken and acceptance rate. Posts nothing.
Drafts through batch.Drafter like the bot: one LLM call per mode per model, more if a batch fails to parse
(counted in data/llm_usage.json), and a few feed reads for targets.
"""
import argparse
import pathlib
import random
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import capturethenarrative as ctn  # noqa: E402
from swan_bot import batch, config, content  # noqa: E402
from swan_bot.llm import Generator  # noqa: E402
from swan_bot.targeting import Targeter  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=4, help="reply jobs (plus n//2 posts)")
    ap.add_argument("--models", help="comma list; default: every model in the chain")
    ap.add_argument("--size", type=int, default=batch.MAX_SIZE, help="items per LLM call (the bot uses --batch)")
    args = ap.parse_args()
    config.load_env()
    gen = Generator(config.team_code())
    social = ctn.LegitSocial(max_retries=2)
    targeter = Targeter(social, log=lambda r: None)
    targeter.refresh(force=True)
    personas = random.sample(content.PERSONAS, k=len(content.PERSONAS))
    jobs = []
    while len(jobs) < args.n:
        cand = targeter.next_target(set(), set(), {})
        if not cand:
            break
        p = personas[len(jobs) % len(personas)]
        jobs.append(dict(mode="reply", rec={"persona": p["key"]}, target=cand["post"], frame=cand["frame"],
                         wants=cand["wants"], context=cand["context"]))
    for i in range(max(1, args.n // 2)):
        p = personas[-(i + 1)]
        jobs.append(dict(mode="post", rec={"persona": p["key"]}, frame=content.pick_frame(p)))
    drafter = batch.Drafter(gen, size=args.size)
    print(f"{len(jobs)} jobs\n")
    models = args.models.split(",") if args.models else [m for _, m in gen.chain]
    summary = []
    for model in models:
        t0 = time.time()
        results = drafter.draft(jobs, headline=targeter.headline, models={model}, rng=random.Random(1))
        took = time.time() - t0
        if results is None:
            print(f"##### {model}: unavailable\n")
            continue
        ok = sum(bool(r["text"]) for r in results)
        print(f"##### {model} ({took:.1f} s)")
        for r in results:
            job = r["job"]
            body = (job.get("target") or {}).get("body") or ""
            who = content.PERSONA_BY_KEY[job["rec"]["persona"]]["name"]
            if body:
                print(f"  [{job['mode']} {job['frame']}] citizen: {body[:120]!r}")
            print(f"  {who}: {'OK' if r['text'] else 'REJECT ' + str(r['why'])} | {(r['raw'] or '')[:320]!r}\n")
        summary.append((model, ok, len(jobs), took))
    print("model | accepted | seconds")
    for model, ok, n, took in summary:
        print(f"  {model:28} {ok}/{n}  {took:5.1f}")


if __name__ == "__main__":
    main()
