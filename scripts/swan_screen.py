"""Read-only screening pass: one targeting refresh with a funnel of why each candidate is kept or dropped, then
dry drafts (real prompts + quality gate + repair, bot.draft_checked) for the best replies and for posts across every persona.
Nothing is registered or posted. Dry only: citizens we already answered are still drafted for, to judge reply quality.

    LLM_RPM=6 python scripts/swan_screen.py data/screen.json --replies 4 --posts 6 --seed 7

Use the same --seed before and after a prompt change so both runs draft the same personas, frames and shapes
(targets come from the live feed, so replies differ run to run). The Gemini key is shared with EC2: keep LLM_RPM <= 6.
"""
import argparse
import json
import pathlib
import random
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import capturethenarrative as ctn  # noqa: E402
from swan_bot import config, content  # noqa: E402
from swan_bot.bot import ARMS, REJECT_ARMS, Accounts, build_prompt, draft_checked, load_json  # noqa: E402
from swan_bot.llm import Generator  # noqa: E402
from swan_bot.targeting import Targeter, messengers, soft_yes  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("out", type=pathlib.Path, help="JSON file to write (drafts, rejects, targeting funnel)")
ap.add_argument("--replies", type=int, default=4)
ap.add_argument("--posts", type=int, default=6)
ap.add_argument("--seed", type=int, default=None, help="fix personas, frames and shapes across runs")
args = ap.parse_args()
out, n_replies, n_posts = args.out, args.replies, args.posts
if args.seed is not None:
    random.seed(args.seed)

config.load_env()
config.assigned_side()
gen = Generator(config.team_code())
social = ctn.LegitSocial()
print("LLM:", gen.describe(), "| pacing", round(gen.min_gap, 1), "s per call per model")
targeter = Targeter(social, log=lambda r: print("refresh:", r))
targeter.refresh(force=True)

state = load_json(config.STATE_FILE, {})        # local state: stale (EC2 is the writer), reported but not obeyed
replied = set(state.get("replied_posts", []))
contacted = {a for a, ts in state.get("contacted", {}).items() if time.time() - ts < config.CONTACT_COOLDOWN_S}
funnel = []
for pid, c in sorted(targeter.candidates.items(), key=lambda kv: -kv[1]["score"]):
    author = c["post"]["author_id"]
    if pid in replied:
        why = "already replied (local state)"
    elif str(author) in contacted:
        why = "contacted < 3 days (local state)"
    elif not targeter.undecided(author):
        why = "states a firm vote in recent posts"
    else:
        why = "ok"
    funnel.append(dict(pid=pid, author=author, frame=c["frame"], wants=c["wants"], identity=c.get("identity"),
                       score=round(c["score"], 2), source=c["source"], soft_yes=soft_yes(c["post"].get("body")),
                       why=why, text=(c["post"].get("body") or "")[:300], context=c.get("context")))
print("funnel:", {w: sum(f["why"] == w for f in funnel) for w in {f["why"] for f in funnel}})

accounts = Accounts(None, live=False)
accounts.records = [dict(username=f"(dry){p['handle']}", persona=p["key"], status="active", last_write=0)
                    for p in content.PERSONAS]
recent = list(state.get("recent_texts", []))[-300:]
recent_shapes, drafts, rejects = [], [], []


def draft(job):
    persona, system, user = build_prompt(job, targeter, recent_shapes)
    target = job.get("target") or {}

    def rejected(why, raw, backend, repaired):
        meta = job["meta"]
        rejects.append({"why": why, "mode": job["mode"], "persona": persona["key"], "voice": meta.get("voice"),
                        "shape": meta.get("shape"), "repair": repaired, "raw": raw,
                        **{k: meta.get(k) for k in REJECT_ARMS}})
        print(f"REJ [{job['mode']}] ({why}{', after repair' if repaired else ''}) {persona['name']}: {raw[:90]}")

    text, backend, repair = draft_checked(gen, job, system, user, recent, rejected)   # the bot's own loop
    if backend is None:
        print("no model available; stopping"); return False
    meta = job["meta"]
    if text:
        recent.append(text)
        if job["mode"] == "post":
            recent_shapes.append(meta.get("shape"))
        drafts.append({"act": job["mode"], "persona": persona["key"], "frame": job["frame"], "backend": backend,
                       "text": text, "source": job.get("source"), "context": job.get("context"),
                       "target_text": target.get("body"), "target_author": target.get("author_id"),
                       "identity": job.get("identity"), "repair": repair,
                       "messenger_match": bool(job.get("identity")) and persona["key"] in messengers(job.get("identity")),
                       "catchphrase": content.catchphrase_in(text),
                       **{k: meta.get(k) for k in ("shape", "hook", "voice", "pillar", "tag", "now", "storyline")},
                       **{k: meta.get(k) for k in ARMS}})
        print(f"OK  [{job['mode']}|{meta.get('voice')}|{meta.get('shape')}{'|repaired ' + repair if repair else ''}] "
              f"{persona['name']}: {text[:90]}")
    return True


# dry only: citizens we already answered are fair game for seeing reply quality; hospital/COVID fears first
usable_t = [f for f in funnel if not f["why"].startswith("states a firm")]
usable_t.sort(key=lambda f: (content.rebuttal_for(f["text"]) is None, f["why"] != "ok", -f["score"]))
ok_targets = usable_t[:n_replies]
jobs = []
for f in ok_targets:
    c = targeter.candidates[f["pid"]]
    rec = accounts.eligible(c["frame"], prefer=messengers(c.get("identity")))
    rec["last_write"] = time.time()
    jobs.append(dict(mode="reply", rec=rec, target=c["post"], frame=c["frame"], wants=c["wants"],
                     context=c["context"], source=c["source"], identity=c.get("identity")))
posters = [p for p in content.PERSONAS] * 2
random.shuffle(posters)
for p in posters[:n_posts]:
    jobs.append(dict(mode="post", rec={"persona": p["key"]}, frame=content.pick_frame(p)))
random.shuffle(jobs)
for job in jobs:
    if not draft(job):
        break

out.write_text(json.dumps(dict(drafts=drafts, rejects=rejects, funnel=funnel, llm_calls=gen.calls), indent=1))
print(f"done: {len(drafts)} drafts, {len(rejects)} rejects, calls {gen.calls} -> {out}")
