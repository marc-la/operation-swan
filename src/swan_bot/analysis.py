"""The experiments' arithmetic (todo/13): portal activity lines, intervals, per-arm tables. No I/O, no network.

scripts/import_activity.py parses the portal's activity export with parse_activity; scripts/experiment_report.py
builds the morning report from the tables here.
"""
import collections
import datetime as dt
import math
import re

Z90 = 1.645

# "NPC engagement (×2 points): 8 views, 2 likes and 1 primary contribution to a change of mind towards your side"
_HEAD = re.compile(r"^\s*(?P<cat>[^:(]+?)\s*(?:\((?:x|×)\s*(?P<mult>[\d.]+)\s*points?\))?\s*:\s*(?P<body>.*)$", re.I)
_ITEM = re.compile(r"^(?P<n>\d+)\s+(?P<what>.+)$")
_PLAIN = {"view": "views", "like": "likes", "repost": "reposts", "repl": "replies", "follow": "follows",
          "unfollow": "unfollows", "comment": "replies"}


def _key(what):
    w = what.lower()
    if "mind" in w or "contribution" in w:
        kind = "primary" if "primary" in w else ("contribution" if "contribution" in w else "change")
        direction = ("towards" if "towards your side" in w else "away" if "away from your side" in w
                     else "neither" if "neither" in w else "other")
        return f"mind_{kind}_{direction}"
    first = w.split()[0]
    for stem, key in sorted(_PLAIN.items(), key=lambda kv: -len(kv[0])):    # "unfollow" before "follow"
        if first.startswith(stem):
            return key
    return "other:" + w[:40]


def parse_activity(text):
    """{"category", "multiplier", counts...} from one activity-log line. Change-of-mind items become
    mind_<primary|contribution|change>_<towards|away|neither>; the totals towards / away / neither add them up."""
    m = _HEAD.match(text or "")
    out = {"category": (m.group("cat").strip() if m else None), "multiplier": float(m.group("mult")) if m and
           m.group("mult") else None}
    body = m.group("body") if m else (text or "")
    counts = collections.Counter()
    for part in re.split(r",\s*|\s+and\s+(?=\d)", body):
        im = _ITEM.match(part.strip())
        if im:
            counts[_key(im.group("what"))] += int(im.group("n"))
    out.update(counts)
    for d in ("towards", "away", "neither"):
        out[d] = sum(v for k, v in counts.items() if k.startswith("mind_") and k.endswith("_" + d))
    return out


def wilson(k, n, z=Z90):
    """(rate, lo, hi): the Wilson interval (90% by default). (None, None, None) when n is 0."""
    if not n:
        return None, None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


def ts_of(iso):
    return dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()


def block_window(block_id):
    """(start, end) epoch seconds of a switchback block id "dim:period:n"."""
    _, period, n = block_id.rsplit(":", 2)
    return int(n) * int(period), (int(n) + 1) * int(period)


def latest_by_post(rows):
    """{post_id: the latest-check record} (outcome or follow-up), ignoring error records."""
    out = {}
    for r in rows:
        if r.get("error") is not None or r.get("post_id") is None:
            continue
        if r["post_id"] not in out or r.get("check", 0) >= out[r["post_id"]].get("check", 0):
            out[r["post_id"]] = r
    return out


LABELLED = ("moved_no", "moved_yes", "no_change", "unclear")    # silent and private are left out of the rate


def arm_rows(writes, dim, outcomes, followups, trending_ids=frozenset(), value=None):
    """One row per arm of `dim`: n writes, per-post citizen engagement (latest outcome), follow-up labels and the
    moved-to-No rate with its 90% interval, Trending entries. `value(write)` overrides how the arm is read."""
    value = value or (lambda w: w.get(dim))
    groups = collections.defaultdict(list)
    for w in writes:
        v = value(w)
        if v is not None:
            groups[v].append(w)
    rows = []
    for arm, ws in groups.items():
        outs = [outcomes[w["post_id"]] for w in ws if w["post_id"] in outcomes]
        fus = [followups[w["post_id"]] for w in ws if w["post_id"] in followups]
        labels = collections.Counter(f.get("label") for f in fus)
        labelled = sum(labels[x] for x in LABELLED)
        rate, lo, hi = wilson(labels["moved_no"], labelled)
        mean = (lambda key: sum(o.get(key) or 0 for o in outs) / len(outs)) if outs else (lambda key: None)
        rows.append(dict(arm=arm, n=len(ws), measured=len(outs), views=mean("views"),
                         cit_likes=mean("citizen_likes"), cit_replies=mean("citizen_replies"),
                         hidden=sum(o.get("hidden_or_gone") is not None for o in outs),
                         followups=len(fus), labelled=labelled, moved_no=labels["moved_no"],
                         moved_yes=labels["moved_yes"], silent=labels["silent"], rate=rate, lo=lo, hi=hi,
                         trending=sum(w["post_id"] in trending_ids for w in ws)))
    return sorted(rows, key=lambda r: (-r["n"], str(r["arm"])))


def separated(rows, min_labelled=30):
    """Arms whose moved-to-No interval clears every other arm's (only arms with ≥ min_labelled follow-ups)."""
    ok = [r for r in rows if r["labelled"] >= min_labelled and r["rate"] is not None]
    out = []
    for r in ok:
        others = [o for o in ok if o is not r]
        if others and all(r["lo"] > o["hi"] for o in others):
            out.append((r["arm"], "above"))
        elif others and all(r["hi"] < o["lo"] for o in others):
            out.append((r["arm"], "below"))
    return out
