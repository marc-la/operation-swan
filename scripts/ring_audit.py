"""Read-only ring audit: how much does a post look like coordinated amplification? (our self-check, docs/06-strategy/amplification.md; Blue evidence, todo/07)

Scores each post on the tells Blue teams and the literature use (CopyCatch lockstep, like-farm timing, QUT
coordination toolkit's 60 s co-action window, Legit Social's consecutive-id reply rings):
  team_like   share of likers that are team accounts (created after launch)
  first2m     share of likes in the first 2 min after posting
  burst60     largest number of likes inside any 60 s window
  runs        longest run of near-consecutive account ids (gap <= 3) among likers + repliers
  overlap     mean Jaccard of this post's team likers with the other audited posts' (lockstep across posts)

    python scripts/ring_audit.py --trending            # the top of Trending (the leaders' rings)
    python scripts/ring_audit.py --ours 20             # our last 20 amplified posts (from logs/swan_actions.jsonl)
    python scripts/ring_audit.py 66490 67723           # given posts
"""
import argparse
import datetime as dt
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import capturethenarrative as ctn  # noqa: E402

from swan_bot import config  # noqa: E402


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def longest_run(ids, gap=3):
    ids, best, cur = sorted(set(ids)), 0, 0
    for a, b in zip(ids, ids[1:]):
        cur = cur + 1 if b - a <= gap else 0
        best = max(best, cur)
    return best + 1 if ids else 0


def audit(social, pid):
    post = social.get_post(pid)
    t0 = ts(post["created_at"])
    likers = list(social.iterate(social.likers, pid, max_items=200))
    replies = list(social.iterate(social.replies, pid, max_items=200))
    team = [x["account_id"] for x in likers if x["account_id"] > config.CITIZEN_MAX_ID]
    delays = sorted(ts(x["liked_at"]) - t0 for x in likers if x.get("liked_at"))
    burst = max((sum(1 for d in delays if a <= d < a + 60) for a in delays), default=0)
    rep_ids = [r["author_id"] for r in replies]
    return dict(post_id=pid, author=post["author_id"], likes=len(likers), replies=len(replies),
                team_like=len(team) / max(len(likers), 1),
                first2m=sum(d < 120 for d in delays) / max(len(delays), 1),
                median_min=(statistics.median(delays) / 60) if delays else None, burst60=burst,
                runs=longest_run([x["account_id"] for x in likers if x["account_id"] > config.CITIZEN_MAX_ID]
                                 + [i for i in rep_ids if i > config.CITIZEN_MAX_ID]),
                team_replies=sum(i > config.CITIZEN_MAX_ID for i in rep_ids), _team_likers=set(team))


def ring_score(r):
    """0-100, higher = more ring-like. Weights are a judgement call; compare us against the leaders, not 0."""
    return round(100 * (0.3 * r["team_like"] + 0.2 * r["first2m"] + 0.15 * min(r["burst60"] / 10, 1)
                        + 0.2 * min(r["runs"] / 10, 1) + 0.15 * r["overlap"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("posts", nargs="*", type=int)
    ap.add_argument("--trending", action="store_true")
    ap.add_argument("--ours", type=int, default=0, help="our last N amplified posts")
    args = ap.parse_args()
    social = ctn.LegitSocial()
    ids = list(args.posts)
    if args.trending:
        ids += [p["post_id"] for p in social.feed_trending(limit=35)]
    if args.ours:
        plans = [json.loads(line) for line in open(config.ACTIONS_LOG) if '"amp_plan"' in line]
        ids += [p["post_id"] for p in plans if p.get("live") and p.get("post_id")][-args.ours:]
    rows = []
    for pid in ids:
        try:
            rows.append(audit(social, pid))
        except ctn.APIError as e:
            print(f"#{pid}: {e.status} {e.message}")
    for r in rows:
        others = [o["_team_likers"] for o in rows if o is not r and o["_team_likers"]]
        r["overlap"] = (statistics.mean(len(r["_team_likers"] & o) / len(r["_team_likers"] | o) for o in others)
                        if others and r["_team_likers"] else 0.0)
    print(f"{'post':>7} {'author':>6} {'likes':>5} {'team%':>5} {'<2m%':>5} {'med':>5} {'b60':>4} {'run':>4} "
          f"{'tRep':>4} {'ovl':>4} {'RING':>4}")
    for r in sorted(rows, key=ring_score, reverse=True):
        med = f"{r['median_min']:.0f}m" if r["median_min"] is not None else "-"
        print(f"{r['post_id']:>7} {r['author']:>6} {r['likes']:>5} {r['team_like']:>5.0%} {r['first2m']:>5.0%} "
              f"{med:>5} {r['burst60']:>4} {r['runs']:>4} {r['team_replies']:>4} {r['overlap']:>4.2f} {ring_score(r):>4}")


if __name__ == "__main__":
    main()
