"""Citizens above id 2343 (todo/48): a score in [0, 1] that an account is an NPC citizen, from its own newest page of
posts and its profile. Pure: no reads, no files (scripts/npc_scan.py reads and writes data/npc_scores.json).

Why: config.is_citizen knows the 2,332 seeded ids (12-2343), the briefing says "just over 6,000" citizens, and ids
4400-4790 (19 Oct 17:00-20:53 UTC) and others hold accounts that post like citizens. The same bands hold team bots
(ours too: 6 of our accounts sit in 4400-4790), so an id range is not safe: each account is judged on what it does.

What a citizen looks like (27 Oct, 320 seeded citizens against 900+ team accounts): it is online a few minutes every
day or two and writes 2-8 posts inside one minute or two (a session), then goes quiet; a team bot writes all day, one
post every few minutes, or in hour-long runs. Style helps a little (giphy links, lowercase, first names). Features are
measured on ONE page (the newest 100 posts, what one account_posts read returns), the same in training and live.

The model is a logistic regression on standardised features, fitted by scripts/npc_scan.py --fit on labelled ids and
pasted into MODEL with its date; explain() gives each feature's share of a score.
"""
import datetime as dt
import math
import re
import statistics as st

SESSION_GAP_S = 15 * 60             # posts closer than this are one session (citizens: 1-5 min online every ~2 days)
BURST_S = 120                       # a post this soon after the one before counts as a burst (a citizen's session)
LIVE_MIN_POSTS = 3                  # fewer posts than this: no score (None), too little to judge
MIN_SESSIONS = 2                    # ...or fewer sessions: one sitting says nothing about the rhythm
GIPHY = re.compile(r"giphy\.com", re.I)
UPPER = re.compile(r"[A-Z]")
# What the model reads (27 Oct). Tried and left out, weight ~0 in the fit: the creation pace of the id neighbours (the whole
# platform registered about one account every 30 s on 19-21 Oct, so a seeding-paced run says little; scripts/citizen_watch.py),
# emoji, a hex tail on the username (civic_voice_08_bc923e), any display word inside the username.
FEATURES = ("sess_per_day", "posts_per_sess", "sess_len_min", "burst", "gap_h", "hours_per_day", "reply", "repost", "giphy",
            "lower", "chars", "dup", "at", "name_match", "two_names")


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def rows(posts):
    """[(t, kind, body, giphy)] oldest first, from platform post dicts or the census pull rows (k, t, b, e)."""
    out = []
    for p in posts:
        if "created_at" in p:
            t, k, b = p["created_at"], p.get("kind") or "post", p.get("body") or ""
            e = (p.get("embed") or {}).get("kind") if isinstance(p.get("embed"), dict) else p.get("embed")
        else:
            t, k, b, e = p["t"], p.get("k") or "post", p.get("b") or "", p.get("e")
        out.append((ts(t), k, b, e == "giphy" or bool(GIPHY.search(b))))
    return sorted(out)


def sessions(times, gap=SESSION_GAP_S):
    """[[t, ...]] runs of posts each within `gap` of the one before."""
    out = []
    for t in sorted(times):
        if out and t - out[-1][-1] <= gap:
            out[-1].append(t)
        else:
            out.append([t])
    return out


def _words(s):
    return {w for w in re.split(r"[^a-z]+", (s or "").lower()) if len(w) >= 3}


def features(account, posts):
    """{name: value} (FEATURES) for one account, or None under LIVE_MIN_POSTS posts or MIN_SESSIONS sessions. account: a
    get_account / census dict (username, display_name), or None; posts: its newest page (reposts count for the rhythm)."""
    r = rows(posts)
    if len(r) < LIVE_MIN_POSTS:
        return None
    times = [x[0] for x in r]
    ss = sessions(times)
    if len(ss) < MIN_SESSIONS:
        return None                                                     # one sitting shows no rhythm (a new account, a burst)
    span_d = max((times[-1] - times[0]) / 86400, 0.25)
    gaps = [b[0] - a[-1] for a, b in zip(ss, ss[1:])]
    texts = [x[2] for x in r if x[1] != "repost" and x[2]]
    n_t = max(len(texts), 1)
    burst = sum(1 for a, b in zip(times, times[1:]) if b - a <= BURST_S)
    name, disp = (account or {}).get("username") or "", (account or {}).get("display_name") or ""
    return dict(
        sess_per_day=len(ss) / span_d,                                   # seeded citizens ~0.8 a day, team bots 9-30
        posts_per_sess=len(times) / len(ss),
        sess_len_min=st.median([(s[-1] - s[0]) / 60 for s in ss]),
        burst=burst / (len(times) - 1),                                  # share of posts under BURST_S after the last
        gap_h=math.log1p(st.median(gaps) / 3600),                        # citizens ~1-2 days between sessions
        hours_per_day=len({int(t // 3600) for t in times}) / span_d,      # distinct clock hours with a post, a day
        reply=sum(x[1] == "reply" for x in r) / len(r),
        repost=sum(x[1] == "repost" for x in r) / len(r),
        giphy=sum(x[3] for x in r) / len(r),
        lower=sum(not UPPER.search(b) for b in texts) / n_t,
        chars=math.log1p(st.median([len(b) for b in texts])) if texts else 0.0,
        dup=1 - len(set(texts)) / n_t,                                   # the same text twice: a template
        at=sum(b.startswith("@") for b in texts) / n_t,                  # '@chloerunning3 but what about...'
        name_match=float(bool(_words(disp) & _words(name))),            # team bots: 'calvin_dunn48' / 'Calvin Dunn'
        two_names=float(len(disp.split()) >= 2 and all(w[:1].isupper() for w in disp.split()[:2])),
    )


# Fitted 2026-10-27 on every label (282 seeded citizens with 2+ sessions; 663 team accounts: 601 moderator-hidden authors,
# 55 of ours, 7 civic_voice_NN_hex names), class-balanced, l2 1.0. mean/sd standardise; w per feature; b the bias.
# 5-fold out-of-fold: cut 0.3 recall 1.000 at 0.3% of team accounts; cut 0.9 recall 0.996 and no team account. The biggest
# terms: days between sessions, clock hours a day, two-word display name, bursts. todo/48 has the read-out.
MODEL = dict(date="2026-10-27", b=-3.7307,
             w=dict(sess_per_day=-0.8693, posts_per_sess=-0.2508, sess_len_min=-0.2271, burst=1.1014, gap_h=2.5256,
                    hours_per_day=-1.233, reply=0.5942, repost=-0.3745, giphy=0.786, lower=0.4568, chars=-0.8158,
                    dup=-0.3869, at=0.1683, name_match=-0.4114, two_names=1.1163),
             mean=dict(sess_per_day=17.0134, posts_per_sess=3.8934, sess_len_min=7.3885, burst=0.2546, gap_h=1.4266,
                       hours_per_day=12.7616, reply=0.5863, repost=0.2389, giphy=0.0837, lower=0.1109, chars=5.1676,
                       dup=0.0305, at=0.0409, name_match=0.6138, two_names=0.9058),
             sd=dict(sess_per_day=14.2029, posts_per_sess=6.1328, sess_len_min=30.7046, burst=0.3032, gap_h=1.4425,
                     hours_per_day=9.4764, reply=0.2807, repost=0.2803, giphy=0.1492, lower=0.2352, chars=0.9111,
                     dup=0.1621, at=0.1119, name_match=0.4869, two_names=0.2921))


def score(f, model=None):
    """P(citizen) in [0, 1], or None for no features. A missing feature (None) sits at its mean (no contribution)."""
    model = model or MODEL
    if f is None or model is None:
        return None
    z = model["b"] + sum(c for _, c in contributions(f, model))
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))


def contributions(f, model=None):
    """[(feature, its term in the logit)], largest first by size."""
    model = model or MODEL
    out = []
    for k, w in model["w"].items():
        v = f.get(k)
        if v is None:
            continue
        out.append((k, w * (v - model["mean"][k]) / model["sd"][k]))
    return sorted(out, key=lambda kv: -abs(kv[1]))


def explain(f, model=None, n=4):
    """'sess_per_day -2.1, burst +1.3, ...': the n biggest terms, for logs and the dashboard."""
    return ", ".join(f"{k} {c:+.1f}" for k, c in contributions(f, model)[:n])


def _solve(a, y):
    """x with a x = y (Gauss-Jordan with partial pivoting; a is small and positive definite here)."""
    n = len(a)
    m = [row[:] + [v] for row, v in zip(a, y)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        piv = m[c][c] or 1e-12
        m[c] = [v / piv for v in m[c]]
        for r in range(n):
            if r != c and m[r][c]:
                f = m[r][c]
                m[r] = [a_ - f * b_ for a_, b_ in zip(m[r], m[c])]
    return [m[r][n] for r in range(n)]


def fit(xs, ys, names, l2=1.0, iters=25, weights=None):
    """A logistic regression with an L2 penalty on the weights (not the bias), by Newton steps: pure python, the box
    has no sklearn. xs: [{name: value}], ys: 0/1, weights: per-row weights (class balance). A missing value takes the
    feature's mean. Returns a MODEL dict."""
    weights = weights or [1.0] * len(xs)
    mean, sd = {}, {}
    for k in names:
        vs = [x[k] for x in xs if x.get(k) is not None]
        mean[k] = st.fmean(vs) if vs else 0.0
        sd[k] = (st.pstdev(vs) if len(vs) > 1 else 0.0) or 1.0
    z = [[1.0] + [0.0 if x.get(k) is None else (x[k] - mean[k]) / sd[k] for k in names] for x in xs]
    d = len(names) + 1
    beta = [0.0] * d
    for _ in range(iters):
        g = [0.0] * d
        h = [[0.0] * d for _ in range(d)]
        for zi, y, wt in zip(z, ys, weights):
            p = 1 / (1 + math.exp(-max(-30.0, min(30.0, sum(a * c for a, c in zip(beta, zi))))))
            r, s = wt * (p - y), wt * p * (1 - p)
            for j in range(d):
                g[j] += r * zi[j]
                sj = s * zi[j]
                hj = h[j]
                for k in range(j, d):
                    hj[k] += sj * zi[k]
        for j in range(d):
            for k in range(j):
                h[j][k] = h[k][j]
            if j:
                g[j] += l2 * beta[j]
                h[j][j] += l2
        step = _solve(h, g)
        beta = [b_ - s_ for b_, s_ in zip(beta, step)]
        if max(abs(s_) for s_ in step) < 1e-6:
            break
    return dict(w=dict(zip(names, beta[1:])), b=beta[0], mean=mean, sd=sd)
