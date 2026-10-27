#!/usr/bin/env python
"""Score accounts above id 2343 as NPC citizens (todo/48, swan_bot/npc.py). Read-only on Legit Social: account_posts and
get_account only, no login, no team code, paced at --rate reads a minute (the 300/min buckets are team-wide and shared
with the live bot and swan_blue), backing off on 429 and when a bucket runs low. Never calls a feed: the authors come
from the bot's own Latest snapshot (data/latest_snapshot.json).

    python scripts/npc_scan.py --dry                 # read + score the snapshot's authors > 2343, print; no file written
    python scripts/npc_scan.py                       # ...and merge them into data/npc_scores.json (config.NPC_SCORES_FILE)
    python scripts/npc_scan.py --ids 4580 4516       # these accounts as well
    python scripts/npc_scan.py --fit L.json --pages P.json   # offline refit, no reads: prints MODEL and the held-out cuts

Scores are only read through config (likely_citizen, npc_target, blue_citizen); both switches that use them ship OFF.
An account scored within --fresh-h hours is not read again; within one run no account is read twice. Profiles
(username, display name) come from the newest data/rival_census/census-*.jsonl when there is one, else get_account.
--fit takes L.json = {"citizen": [ids], "team": [ids], "check": {name: [ids]}} and P.json = {id: [posts]} (platform
dicts or census pull rows) and splits the labels 70/30 by a hash of the id.
"""
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import capturethenarrative as ctn  # noqa: E402

from swan_bot import config, npc  # noqa: E402

CENSUS_DIR = config.DATA / "rival_census"
RATE = 40                   # reads a minute, all routes together (well under 300/min per route, shared team-wide)
SPARE = 120                 # stop for the bucket's reset when fewer than this are left (the bot and Blue need theirs)
CUTS = (0.1, 0.2, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95)


def now_iso(t=None):
    return dt.datetime.fromtimestamp(time.time() if t is None else t, dt.timezone.utc).isoformat()


def snapshot_authors(snap, ours=()):
    """Ids above CITIZEN_MAX_ID that wrote a post, reply or repost in the snapshot, not ours, most active first."""
    n = {}
    for p in (snap or {}).get("posts") or []:
        a = p.get("author_id") or 0
        if a > config.CITIZEN_MAX_ID and a not in ours:
            n[a] = n.get(a, 0) + 1
    return sorted(n, key=lambda a: (-n[a], a))


def latest_census(d=CENSUS_DIR):
    """{id: account row} from the newest census-*.jsonl, or {} (profiles then come from get_account)."""
    files = sorted(d.glob("census-*.jsonl")) if d.exists() else []
    out = {}
    for f in files[-1:]:
        for line in f.read_text().splitlines():
            try:
                a = json.loads(line)
                out[a["account_id"]] = a
            except (ValueError, KeyError):
                continue
    return out


class Reader:
    """Paced reads: at most `rate` a minute; a bucket under SPARE waits its reset; a 429 waits its Retry-After and two in
    a row stop the run (RuntimeError). Counts every call in self.calls."""

    def __init__(self, social, rate=RATE, sleep=time.sleep, clock=time.time):
        self.social, self.gap, self.sleep, self.clock = social, 60.0 / rate, sleep, clock
        self.calls, self.last, self.strikes = 0, 0.0, 0

    def __call__(self, fn, *a, **kw):
        wait = self.last + self.gap - self.clock()
        if wait > 0:
            self.sleep(wait)
        while True:
            self.last = self.clock()
            self.calls += 1
            try:
                out = fn(*a, **kw)
            except ctn.RateLimited as e:
                self.strikes += 1
                if self.strikes >= 2:
                    raise RuntimeError("two 429s in a row: stopping the scan") from e
                self.sleep(max(e.retry_after or 30, 10))
                continue
            self.strikes = 0
            rl = self.social.rate_limit
            if rl and rl.remaining < SPARE:
                self.sleep(max(rl.reset, 5))
            return out


def score_account(read, social, aid, census):
    """{s, n, at, why} for one account (s None: too few posts or unreadable). Reads its newest page (and its profile
    when the census has none)."""
    rec = dict(at=now_iso(), s=None, n=0)
    try:
        prof = census.get(aid) or read(social.get_account, aid)
        posts = list(read(social.account_posts, aid, limit=100))
    except ctn.APIError as e:
        return dict(rec, err=e.status)
    f = npc.features(prof, posts)
    rec["n"] = len(posts)
    if f is not None:
        rec.update(s=round(npc.score(f), 4), why=npc.explain(f))
    return rec


def merge(old, new, t=None):
    """The scores file: old scores kept, new ones over them, with the build time and model date."""
    t = time.time() if t is None else t
    scores = dict((old or {}).get("scores") or {})
    scores.update({str(k): v for k, v in new.items()})
    return dict(built=now_iso(t), built_ts=t, model=(npc.MODEL or {}).get("date"), target_min=config.NPC_TARGET_MIN,
                blue_min=config.NPC_BLUE_MIN, scores=scores)


def write_atomic(path, obj):
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, separators=(",", ":")))
    tmp.replace(path)


def held_out(i, share=0.3):
    return int(hashlib.sha256(str(i).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < share


def cut_table(scored, cuts=CUTS):
    """[(cut, precision, recall, fpr, tp, fp, fn)] for [(score, label 0/1)]."""
    out = []
    pos = sum(y for _, y in scored)
    neg = len(scored) - pos
    for c in cuts:
        tp = sum(1 for s, y in scored if s >= c and y)
        fp = sum(1 for s, y in scored if s >= c and not y)
        out.append((c, tp / max(tp + fp, 1), tp / max(pos, 1), fp / max(neg, 1), tp, fp, pos - tp))
    return out


def fit_cmd(labels, pages, census, names=None, l2=1.0):
    """Refit on the 70% train split, print the model, the held-out cut table and the check sets' scores."""
    names = names or [k for k in npc.FEATURES]
    feats = {}
    for i, posts in pages.items():
        f = npc.features(census.get(int(i)), posts)
        if f is not None:
            feats[int(i)] = f
    rows = [(i, 1) for i in labels["citizen"] if i in feats] + [(i, 0) for i in labels["team"] if i in feats]
    train = [(i, y) for i, y in rows if not held_out(i)]
    test = [(i, y) for i, y in rows if held_out(i)]
    npos = sum(y for _, y in train)
    w = [len(train) / (2 * npos) if y else len(train) / (2 * (len(train) - npos)) for _, y in train]   # class balance
    model = npc.fit([feats[i] for i, _ in train], [y for _, y in train], names, l2=l2, weights=w)
    print(json.dumps(model, indent=1))
    print(f"train {len(train)} ({npos} citizens), held out {len(test)} ({sum(y for _, y in test)} citizens)")
    for c, p, r, fpr, tp, fp, fn in cut_table([(npc.score(feats[i], model), y) for i, y in test]):
        print(f"cut {c:.2f}: precision {p:.3f} recall {r:.3f} fpr {fpr:.4f} (tp {tp} fp {fp} fn {fn})")
    for name, ids in (labels.get("check") or {}).items():
        s = sorted(npc.score(feats[i], model) for i in ids if i in feats)
        if s:
            print(f"{name}: n {len(s)}, median {s[len(s) // 2]:.3f}, >= 0.5 {sum(x >= 0.5 for x in s)}")
    return model


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry", action="store_true", help="print only; no data/npc_scores.json")
    ap.add_argument("--ids", type=int, nargs="*", default=[], help="accounts to score as well")
    ap.add_argument("--snapshot", default=str(config.DATA / "latest_snapshot.json"))
    ap.add_argument("--rate", type=float, default=RATE, help="reads a minute (all routes)")
    ap.add_argument("--fresh-h", type=float, default=24.0, help="an account scored this recently is not read again")
    ap.add_argument("--max", type=int, default=400, help="accounts read in one run at most")
    ap.add_argument("--fit", help="labels JSON: refit offline (no reads)")
    ap.add_argument("--pages", help="pages JSON for --fit")
    ap.add_argument("--census", default=str(CENSUS_DIR), help="folder with census-*.jsonl (profiles)")
    args = ap.parse_args()
    census = latest_census(pathlib.Path(args.census))
    if args.fit:
        pages = json.loads(pathlib.Path(args.pages).read_text())
        fit_cmd(json.loads(pathlib.Path(args.fit).read_text()), pages, census)
        return
    if npc.MODEL is None:
        raise SystemExit("npc.MODEL is not set: fit first (--fit)")
    records = json.loads(config.ACCOUNTS_FILE.read_text()) if config.ACCOUNTS_FILE.exists() else []
    ours = {r.get("account_id") for r in records if r.get("account_id")}        # ids only, never another field
    try:
        snap = json.loads(pathlib.Path(args.snapshot).read_text())
    except (OSError, ValueError):
        snap = {}
    try:
        old = json.loads(config.NPC_SCORES_FILE.read_text())
    except (OSError, ValueError):
        old = {}
    t = time.time()
    fresh = {int(k) for k, v in (old.get("scores") or {}).items()
             if v.get("at") and t - npc.ts(v["at"]) < args.fresh_h * 3600}
    todo = [a for a in dict.fromkeys(args.ids + snapshot_authors(snap, ours)) if a not in fresh and a not in ours]
    todo = todo[:args.max]
    social = ctn.LegitSocial(max_retries=0)
    read, new = Reader(social, args.rate), {}
    print(f"{len(todo)} accounts to score ({len(fresh)} fresh in the file), at {args.rate:g} reads a minute", flush=True)
    try:
        for aid in todo:
            new[aid] = score_account(read, social, aid, census)
            r = new[aid]
            if args.dry:
                print(aid, r.get("s"), r.get("n"), r.get("why") or r.get("err"), flush=True)
    except RuntimeError as e:
        print(e)
    s = [r["s"] for r in new.values() if r.get("s") is not None]
    print(f"scored {len(s)} of {len(new)}; reads {read.calls}; >= NPC_TARGET_MIN {sum(x >= config.NPC_TARGET_MIN for x in s)}, "
          f">= NPC_BLUE_MIN {sum(x >= config.NPC_BLUE_MIN for x in s)}")
    if not args.dry and new:
        write_atomic(config.NPC_SCORES_FILE, merge(old, new))
        print("wrote", config.NPC_SCORES_FILE)


if __name__ == "__main__":
    main()
