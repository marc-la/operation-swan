"""Daily theme audit (playbook §3): do our wedge slogans look like people repeating a line, or like a bot ring?

    python scripts/theme_audit.py                  # live writes, the last 24 h, from logs/swan_actions.jsonl
    python scripts/theme_audit.py --hours 72       # a longer window
    python scripts/theme_audit.py --dry-runs       # dry-run drafts instead of live writes
    python scripts/theme_audit.py --strict         # exit 1 if any check is over its limit (for a cron or deploy)

Runs the checks a Blue team's coordination detector would, on our own log: no Legit Social calls.
  - themes and levels: how often each theme went out and how (implicit / echo / attributed / verbatim);
  - exact slogans per account and team-wide, the same slogan from two accounts within 2 h, twice in one thread,
    and where in the post it sat (all at the end is a template);
  - shared phrasing: the share of our writes with a 5-word run another of our accounts also wrote in the same
    hour (Pacheco et al. 2021 co-posting), and the same measure over the window for us and for the citizens we
    replied to (their texts are in our log; ours sampled to the same size), so our repetition is compared with how
    much real people repeat.
It reports and flags; what to change is a human call (the budgets live in src/swan_bot/themes.py).
"""
import argparse
import collections
import json
import pathlib
import random
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import config, themes  # noqa: E402
from swan_bot.analysis import ts_of  # noqa: E402

WRITES = ("post", "reply", "second_voice", "reply_back", "journalist", "thread", "thread_answer")
RUN = 5
_COMMON = themes._COMMON | set("i've i'd it's don't can't won't isn't they their them he she his her be have has "
                               "with from what who which if or as".split())


def records(path, since, dry):
    if not path.exists():
        return []
    out = []
    for line in path.open():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("act") in WRITES and bool(r.get("live")) != dry and r.get("text") and ts_of(r["ts"]) >= since:
            out.append(r)
    return out


def runs(text):
    """5-word runs with at least 2 uncommon words (so "and I'm voting No because" doesn't count)."""
    w = themes.words(re.sub(r"#\w+", " ", text or ""))
    return {w[i:i + RUN] for i in range(len(w) - RUN + 1) if sum(x not in _COMMON for x in w[i:i + RUN]) >= 2}


def shared_rate(items, window=None):
    """Share of (author, ts, text) items with a run some other author also wrote (within `window` s, if given),
    and the most shared runs."""
    by_run = collections.defaultdict(list)
    for author, t, text in items:
        for r in runs(text):
            by_run[r].append((author, t))
    hit, top = 0, collections.Counter()
    for author, t, text in items:
        found = False
        for r in runs(text):
            others = {a for a, tt in by_run[r] if a != author and (window is None or abs(tt - t) <= window)}
            if others:
                found = True
                top[" ".join(r)] = max(top[" ".join(r)], len(others) + 1)
        hit += found
    return (hit / len(items) if items else 0.0), top.most_common(5)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--dry-runs", action="store_true", help="audit dry-run drafts instead of live writes")
    ap.add_argument("--strict", action="store_true", help="exit 1 when a check is over its limit")
    ap.add_argument("--log", type=pathlib.Path, default=config.ACTIONS_LOG)
    args = ap.parse_args()

    now = time.time()
    recs = records(args.log, now - args.hours * 3600, args.dry_runs)
    flags = []
    print(f"theme audit: {len(recs)} {'dry-run' if args.dry_runs else 'live'} writes in the last {args.hours:g} h\n")
    if not recs:
        return 0

    # ---- themes and levels ----
    levels = collections.Counter((r.get("theme"), r.get("theme_level")) for r in recs if r.get("theme"))
    themed = sum(levels.values())
    posts = [r for r in recs if r["act"] == "post"]
    print(f"themed: {themed} of {len(recs)} writes; posts {sum(bool(r.get('theme')) for r in posts)} of {len(posts)}")
    for key in themes.THEMES:
        row = {lv: levels[(key, lv)] for lv in ("implicit", "echo", "attributed", "verbatim")}
        seen = [bool(re.search(themes.THEMES[key]["marks"], r["text"], re.I))
                for r in recs if r.get("theme") == key and r.get("theme_level") == "echo"]
        print(f"  {key:10} " + "  ".join(f"{lv} {n}" for lv, n in row.items()) +
              (f"   echo key words seen {sum(seen)}/{len(seen)}" if seen else ""))
    per_hour = collections.Counter((r.get("theme"), int(ts_of(r["ts"]) // 3600)) for r in recs if r.get("theme"))
    busy = [(k, n) for (k, _), n in per_hour.items() if n > themes.THEME_PER_HOUR]
    if busy:
        flags.append(f"a theme went out more than {themes.THEME_PER_HOUR} times in one hour: {busy}")

    # ---- exact slogans ----
    uses = [(r, k) for r in recs for k in themes.slogans_in(r["text"])]
    print(f"\nexact slogans: {len(uses)} (budget {themes.VERBATIM_PER_DAY} a day team-wide, "
          f"{themes.VERBATIM_PER_ACCOUNT} per account)")
    for (r, k) in uses:
        print(f"  {r['ts'][:16]}  {r.get('persona', '?'):7} {r['act']:7} {k:10} {themes.position(r['text'], k)}")
    days = max(args.hours / 24, 1)
    by_acc = collections.Counter(r.get("persona") for r, _ in uses)
    if len(uses) > themes.VERBATIM_PER_DAY * days:
        flags.append(f"{len(uses)} exact slogans in {args.hours:g} h")
    flags += [f"{p} said {n} exact slogans" for p, n in by_acc.items() if n > themes.VERBATIM_PER_ACCOUNT * days]
    for (a, ka), (b, kb) in zip(uses, uses[1:]):
        if ka == kb and a.get("persona") != b.get("persona") and \
                abs(ts_of(b["ts"]) - ts_of(a["ts"])) < themes.SAME_SLOGAN_GAP_S:
            flags.append(f"{ka} from {a.get('persona')} and {b.get('persona')} under 2 h apart")
    thread = collections.Counter((k, r.get("parent_post") or r.get("target_post") or r.get("post_id"))
                                 for r, k in uses if r["act"] != "post")
    flags += [f"{k} twice in thread {t}" for (k, t), n in thread.items() if n > 1 and t]
    pos = collections.Counter(themes.position(r["text"], k) for r, k in uses)
    if len(uses) >= themes.POSITION_RUN and pos.get("middle", 0) == 0:
        flags.append(f"all {len(uses)} exact slogans sat at the end of the post")
    if uses:
        print(f"  positions: {dict(pos)}")

    # ---- shared phrasing: us within the hour, us vs citizens over the window ----
    ours = [(r.get("persona"), ts_of(r["ts"]), r["text"]) for r in recs]
    hour_rate, hour_top = shared_rate(ours, window=3600)
    our_rate, _ = shared_rate(ours)
    seen, citizens = set(), []
    for r in recs:
        if r.get("target_text") and r.get("target_post") not in seen and r["act"] in ("reply", "second_voice"):
            seen.add(r.get("target_post"))
            citizens.append((r.get("target_author"), ts_of(r["ts"]), r["target_text"]))
    cit_rate, cit_top = shared_rate(citizens)
    if len(ours) > len(citizens) >= 20:     # a bigger sample shares more runs by chance: compare equal sizes
        rng = random.Random(0)
        our_rate = sum(shared_rate(rng.sample(ours, len(citizens)))[0] for _ in range(20)) / 20
    print(f"\nshared {RUN}-word runs across accounts:")
    print(f"  ours, same hour: {hour_rate:.0%} of writes" + "".join(f"\n    {n} accounts: {s!r}" for s, n in hour_top))
    print(f"  ours, whole window (sampled to the citizens' size): {our_rate:.0%}   citizens we replied to "
          f"({len(citizens)}): {cit_rate:.0%}"
          + "".join(f"\n    citizens, {n} authors: {s!r}" for s, n in cit_top[:3]))
    if hour_rate > 0.10:
        flags.append(f"{hour_rate:.0%} of our writes share a {RUN}-word run with another account in the same hour")
    if len(citizens) >= 20 and our_rate > max(cit_rate * 1.5, 0.05):
        flags.append(f"we repeat ourselves more than the citizens do ({our_rate:.0%} vs {cit_rate:.0%})")

    print("\n" + ("\n".join(f"FLAG: {f}" for f in flags) if flags else "no flags"))
    return 1 if flags and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
