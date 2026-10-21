"""What makes a post a report target, and what we say about it (read-only; no platform writes here).

A post qualifies only on evidence of automation (rules §5.2.2, LS.6.5): its author is a team account (registered after
launch, not ours, not verified) AND it carries a like ring or a reply ring. The detail text states the measured
numbers, never the post's side. Our own accounts are left out of every count, so a number we quote is theirs.

Clusters stand in for teams (we can't see team ids): accounts that like and reply to the same posts share a label,
kept in state so a team keeps its label across scans. The daily diminishing rate is counted per label.
"""
import datetime as dt
import re

from swan_bot import config

# evidence classes (todo/07): measured on the leaders' rings, 2026-10-21 (40-130 likes, 83-100% team, 22-26 in 60 s)
LIKE_RING = dict(team_likes=20, share=0.85, early=0.5, burst60=8)   # early = share of team likes in the first 30 min
REPLY_RING = dict(replies=10, authors=6, window_min=60)             # team replies from distinct accounts, in 60 min
# A known ring author's new post, minutes old: this many of its likers and repliers already took part in the same
# author's earlier confirmed ring post, and new accounts are this share of its likes. Lockstep, caught before it's big.
EARLY_RING = dict(overlap=8, share=0.85)
RUN_GAP = 3                                                          # near-consecutive account ids: registered in a batch
MODERATOR_RIGHT = 0.9            # scoring page, 20 Oct PM: "approximately one moderator ruling in ten is wrong"
FIRST, LATER, ACCOUNT = 25, 5, 15


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def is_team(account_id, ours):
    return account_id > config.CITIZEN_MAX_ID and account_id not in ours


def longest_run(ids, gap=RUN_GAP):
    ids, best, cur = sorted(set(ids)), 0, 0
    for a, b in zip(ids, ids[1:]):
        cur = cur + 1 if b - a <= gap else 0
        best = max(best, cur)
    return best + 1 if ids else 0


def audit(social, post, ours, max_items=200):
    """Measure one post: who liked and replied, how fast. post is a feed/get_post dict. Reads only."""
    pid, t0 = post["post_id"], ts(post["created_at"])
    likers = list(social.iterate(social.likers, pid, max_items=max_items))
    replies = list(social.iterate(social.replies, pid, max_items=max_items))
    team_likes = [x for x in likers if is_team(x["account_id"], ours)]
    delays = sorted(ts(x["liked_at"]) - t0 for x in team_likes if x.get("liked_at"))
    burst = max((sum(1 for d in delays if a <= d < a + 60) for a in delays), default=0)
    team_replies = [r for r in replies if is_team(r["author_id"], ours)]
    rdelays = [ts(r["created_at"]) - t0 for r in team_replies]
    in_window = [r for r, d in zip(team_replies, rdelays) if d <= REPLY_RING["window_min"] * 60]
    return dict(
        post_id=pid, author=post["author_id"], created=post["created_at"], root=post.get("reply_to_post_id"),
        likes=len([x for x in likers if x["account_id"] not in ours]), team_likes=len(team_likes),
        early=sum(d < 1800 for d in delays) / max(len(delays), 1), first2m=sum(d < 120 for d in delays),
        burst60=burst, replies=len(replies), team_replies=len(in_window),
        reply_authors=len({r["author_id"] for r in in_window}),
        reply_span_min=round((max(rdelays) - min(rdelays)) / 60) if len(rdelays) > 1 else 0,
        run=longest_run([x["account_id"] for x in team_likes] + [r["author_id"] for r in team_replies]),
        liker_ids=sorted(x["account_id"] for x in team_likes),
        reply_posts=[dict(post_id=r["post_id"], author=r["author_id"], created=r["created_at"]) for r in in_window],
        audited=dt.datetime.now(dt.timezone.utc).isoformat())


def members(a):
    """The team accounts acting on a post: its likers and repliers."""
    return set(a["liker_ids"]) | {r["author"] for r in a["reply_posts"]}


def classes(a):
    """Evidence classes this audit shows: 'reply_ring', 'like_ring', 'early_ring' (strongest first). early_ring needs
    a['overlap'], set by the service for a known ring author's post."""
    out = []
    if a["reply_authors"] >= REPLY_RING["authors"] and a["team_replies"] >= REPLY_RING["replies"]:
        out.append("reply_ring")
    if (a["team_likes"] >= LIKE_RING["team_likes"] and a["team_likes"] >= LIKE_RING["share"] * max(a["likes"], 1)
            and (a["early"] >= LIKE_RING["early"] or a["burst60"] >= LIKE_RING["burst60"])):
        out.append("like_ring")
    if a.get("overlap", 0) >= EARLY_RING["overlap"] and a["team_likes"] >= EARLY_RING["share"] * max(a["likes"], 1):
        out.append("early_ring")
    return out


# ---- what we file: concrete, true, measured. Begins as the platform requires (api-reference: Reporting) ----
def post_detail(a):
    bits = []
    if a["team_likes"]:
        b = f"{a['team_likes']} of its {a['likes']} likes came from accounts registered after the campaign launch"
        if a["first2m"]:
            b += f", {a['first2m']} of them within 2 minutes of posting"
        if a["burst60"] >= 5:
            b += f" ({a['burst60']} inside a single 60-second window)"
        bits.append(b)
    if a["team_replies"] >= REPLY_RING["replies"]:
        bits.append(f"{a['team_replies']} replies from {a['reply_authors']} such accounts arrived within "
                    f"{max(a['reply_span_min'], 1)} minutes")
    if a.get("overlap", 0) >= EARLY_RING["overlap"]:
        bits.append(f"{a['overlap']} of these accounts also liked or replied to its author's earlier post "
                    f"#{a['prior_post']}, which showed the same pattern, so they act as a group")
    if a["run"] >= 5:
        bits.append(f"{a['run']} of these accounts have near-consecutive ids, so they were registered as a batch")
    return "I think that this content is inauthentic (bot) activity because " + "; ".join(bits) + "."


def reply_detail(r, root):
    return (f"I think that this content is inauthentic (bot) activity because it is one of {root['team_replies']} "
            f"replies posted under post #{root['post_id']} within {max(root['reply_span_min'], 1)} minutes by "
            f"{root['reply_authors']} different accounts registered after the campaign launch, and that post's likes "
            f"came {root['team_likes']} of {root['likes']} from the same kind of new accounts.")


def brief(a, root=None):
    """The evidence in a few words, for the dashboard's approval list."""
    if root:
        return (f"1 of {root['team_replies']} ring replies under #{root['post_id']} in {max(root['reply_span_min'], 1)} min; "
                f"root liked {root['team_likes']}/{root['likes']} by new accounts")
    bits = [f"{a['team_likes']}/{a['likes']} likes by new accounts"] if a["team_likes"] else []
    if a["burst60"] >= 5:
        bits.append(f"{a['burst60']} in 60 s")
    if a["team_replies"] >= REPLY_RING["replies"]:
        bits.append(f"{a['team_replies']} ring replies in {max(a['reply_span_min'], 1)} min")
    if a.get("overlap", 0) >= EARLY_RING["overlap"]:
        bits.append(f"{a['overlap']} repeat accounts from its author's ring post #{a['prior_post']}")
    return ", ".join(bits)


def account_detail(account_id, hidden_post, actions, ring_posts):
    shown = ", ".join(f"#{p}" for p in ring_posts[:3])
    return (f"I think that this account is conducting inauthentic (bot) activity because the moderator has already "
            f"hidden its post #{hidden_post} as inauthentic, it has taken {actions}+ actions, and it acts in lockstep "
            f"with a group of accounts registered after the campaign launch that like and reply to the same posts "
            f"within minutes of each other" + (f" (e.g. {shown})." if shown else "."))


# ---- clusters: one label per (presumed) team ----
def label_for(a, labels):
    """The cluster label for an audited post. Accounts already labelled vote; a new group gets 'c<author>'.
    Every account in the post is then filed under the winner (existing labels are never overwritten)."""
    members = [a["author"], *a["liker_ids"], *(r["author"] for r in a["reply_posts"])]
    votes = {}
    for m in members:
        lab = labels.get(str(m))
        if lab:
            votes[lab] = votes.get(lab, 0) + (5 if m == a["author"] else 1)
    lab = max(votes, key=votes.get) if votes and max(votes.values()) >= 3 else f"c{a['author']}"
    for m in members:
        labels.setdefault(str(m), lab)
    return lab


# ---- expected value: what the greedy fill ranks by ----
def rate(n):
    """Paid rate for the (n+1)-th award against one team today (scoring guide §3)."""
    return 1.0 if n < 5 else 0.5 if n < 10 else 0.1


def p_first(age_min, trending, scale=1.0):
    """Chance nobody reported it before us. A prior by age (fresh posts off Trending are rarely reported yet), times
    scale: how our paid-as-first share has compared with this prior so far (service.calibrate)."""
    p = 0.9 if age_min <= 60 else 0.6 if age_min <= 180 else 0.3
    return min(0.97, p * (0.7 if trending else 1.0) * scale)


def post_ev(age_min, trending, strong=1.0, n=0, scale=1.0):
    pf = p_first(age_min, trending, scale)
    return MODERATOR_RIGHT * (FIRST * pf + LATER * (1 - pf)) * rate(n) * strong


def account_ev(n_today):
    return 0.95 * ACCOUNT * rate(n_today)      # rule-based ruling: no moderator error, no lock if dismissed


# ---- measuring first: the portal's points log says which awards paid as first reporter ----
FIRST_RE = re.compile(r"(\d+) first inauthentic reports?", re.I)
LATER_RE = re.compile(r"(\d+) inauthentic reports?", re.I)          # "1 first inauthentic report" doesn't match


def first_later(messages):
    """(paid as first, paid as a later reporter) over portal messages like 'Moderation (x0.5 points): 2 first
    inauthentic reports and 1 inauthentic report' (scoring guide §6)."""
    first = later = 0
    for m in messages:
        first += sum(int(n) for n in FIRST_RE.findall(m or ""))
        later += sum(int(n) for n in LATER_RE.findall(m or ""))
    return first, later
