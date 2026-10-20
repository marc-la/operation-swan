"""Read-only: send the same batch of real drafting jobs to each model in the chain and compare.

    python scripts/llm_compare.py                 # 4 replies + 2 posts, every model in the chain
    python scripts/llm_compare.py -n 6 --models gemini-3.5-flash,openai/gpt-oss-120b
Prints each model's drafts with the quality-gate verdict, time taken and acceptance rate. Posts nothing.
Uses one LLM request per model (counted in data/llm_usage.json) and a few feed reads for targets.
"""
import argparse
import pathlib
import random
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import capturethenarrative as ctn  # noqa: E402
from swan_bot import batch, config, content, quality  # noqa: E402
from swan_bot.llm import Generator  # noqa: E402
from swan_bot.targeting import Targeter  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=4, help="reply jobs (plus n//2 posts)")
    ap.add_argument("--models", help="comma list; default: every model in the chain")
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
    system, user, labels = batch.build_prompt(jobs, targeter.headline)
    print(f"{len(jobs)} jobs, prompt {len(system) + len(user)} chars\n")
    models = args.models.split(",") if args.models else [m for _, m in gen.chain]
    summary = []
    for model in models:
        t0 = time.time()
        raw, used = gen.complete(system, user, json_mode=True, models={model})
        took = time.time() - t0
        if raw is None:
            print(f"##### {model}: unavailable\n")
            continue
        items = batch.parse_items(raw)
        if len(items) < len(jobs):
            print(f"  (raw answer, {len(raw)} chars): {raw[:400]!r}")
        ok, accepted = 0, []
        print(f"##### {model} ({took:.1f} s, {len(items)}/{len(jobs)} items parsed)")
        for label, job in zip(labels, jobs):
            point, text = items.get(label, ("", ""))
            body = (job.get("target") or {}).get("body") or ""
            others = [(j.get("target") or {}).get("body") or "" for j in jobs if j is not job and j.get("target")]
            clean, why = quality.check(text, job["mode"], accepted, target_text=body, wants=job.get("wants") or ())
            if clean and job["mode"] != "post" and not batch.points_at(point, body, others):
                clean, why = None, "mixup"
            ok += bool(clean)
            if clean:
                accepted.append(clean)
            who = content.PERSONA_BY_KEY[job["rec"]["persona"]]["name"]
            if body:
                print(f"  [{label} {job['mode']} {job['frame']}] citizen: {body[:120]!r}")
            print(f"  [{label}] {who}: {'OK' if clean else 'REJECT ' + str(why)} | {text[:320]!r}\n")
        summary.append((model, ok, len(jobs), took))
    print("model | accepted | seconds")
    for model, ok, n, took in summary:
        print(f"  {model:28} {ok}/{n}  {took:5.1f}")


if __name__ == "__main__":
    main()
