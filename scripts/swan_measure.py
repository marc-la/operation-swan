"""Read-only: per-post engagement for everything swan_bot posted, split into citizen vs all.

    python scripts/swan_measure.py            # summary by frame, persona and mode
Citizen = account id <= CITIZEN_MAX_ID (seeded before launch); later-added citizens are missed.
"""
import collections
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import capturethenarrative as ctn  # noqa: E402
from swan_bot import config, jsonl  # noqa: E402


def main():
    posts = [r for r in jsonl.Reader(config.ACTIONS_LOG, contains='"live"') if r.get("live") and r.get("post_id")]
    if not posts:
        print("no live posts logged yet")
        return
    social = ctn.LegitSocial(max_retries=2)
    citizen = lambda aid: 11 < aid <= config.CITIZEN_MAX_ID
    out = []
    for r in posts:
        try:
            c = social.counters(r["post_id"])
            likers = list(social.likers(r["post_id"], limit=50))
            replies = list(social.replies(r["post_id"], limit=50))
        except ctn.APIError as e:
            print("skip", r["post_id"], e.status)
            continue
        out.append({**r, "views": c["view_count"], "likes": c["like_count"], "replies": c["reply_count"],
                    "cit_likes": sum(citizen(l["account_id"]) for l in likers),
                    "cit_replies": sum(citizen(x["author_id"]) for x in replies)})
        time.sleep(0.3)
    for key in ("mode", "frame", "persona"):
        agg = collections.defaultdict(list)
        for o in out:
            agg[o[key]].append(o)
        print(f"\nby {key}: n | avg views | avg likes | avg citizen likes | avg citizen replies")
        for name, g in sorted(agg.items(), key=lambda kv: -sum(x["cit_likes"] + 3 * x["cit_replies"] for x in kv[1]) / len(kv[1])):
            n = len(g)
            print(f"  {name:24} {n:4} | {sum(x['views'] for x in g)/n:6.1f} | {sum(x['likes'] for x in g)/n:5.1f} | "
                  f"{sum(x['cit_likes'] for x in g)/n:5.1f} | {sum(x['cit_replies'] for x in g)/n:5.1f}")
    best = sorted(out, key=lambda o: -(o["cit_likes"] + 3 * o["cit_replies"]))[:5]
    print("\ntop posts by citizen engagement:")
    for o in best:
        print(f"  #{o['post_id']} {o['frame']} cit_likes={o['cit_likes']} cit_replies={o['cit_replies']}: {o['text'][:120]}")


if __name__ == "__main__":
    main()
