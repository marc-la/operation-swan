#!/usr/bin/env python
"""Offline evaluation: do per-account text-embedding features help Blue (todo/43)? Local files only; no platform calls.

Question 1: from an account's posts BEFORE its first hidden post, does embedding structure (dispersion, near-duplicates,
look-alike accounts) predict that it gets a post hidden, beyond behaviour and lexical features we already have?
Question 2: does text carry team identity, i.e. do accounts of one registration fleet look alike, and do the
look-alike accounts of different fleets share a Blue cluster / a fate more than chance?

Needs data/embed/ from scripts/blue_embed_corpus.py and a pull of data/rival_census/ (+ box-0124/ for Blue's state).
Pre-declared rules are in docs/06-strategy/blue-embedding-eval-2026-10-24.md. Writes data/embed/results.json.
"""
import collections
import datetime as dt
import json
import pathlib
import re
import sys

import numpy as np
from sklearn.cluster import MiniBatchKMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from swan_blue import detect, fleets as F  # noqa: E402

D = ROOT / "data" / "rival_census"
E = ROOT / "data" / "embed"
NEW = D / "box-0124"
OLD = D / "box"
K_MIN, WINDOW = 10, 40            # texts needed before the cutoff; newest WINDOW of them are used
NEARDUP = 0.85                    # raw cosine at which two own posts count as near-duplicates (fixed in advance)
LOOKALIKE = 0.85                  # centered-centroid cosine at which two accounts look alike (fixed in advance)
RNG = np.random.default_rng(7)
YES = re.compile(r"\b(vote yes|voting yes|support(ing)? (the )?(proof|requirement)|back the proof)\b", re.I)
NO = re.compile(r"\b(vote no|voting no|oppose|against (the )?(proof|requirement))\b", re.I)


def T(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def load():
    posts = [json.loads(l) for l in open(E / "posts.jsonl")]
    vecs = np.load(E / "vecs.npy").astype(np.float32)
    ids = np.array([p["id"] for p in posts])
    acc = np.array([p["a"] for p in posts])
    ts = np.array([T(p["t"]) for p in posts])
    by = collections.defaultdict(list)
    for i, a in enumerate(acc):
        by[int(a)].append(i)
    by = {a: np.array(sorted(ix, key=lambda i: ids[i])) for a, ix in by.items()}
    return posts, vecs, ids, acc, ts, by


def blue_labels():
    new = json.load(open(NEW / "blue_state.json"))
    old = json.load(open(OLD / "blue_state.json"))
    hv_new = {int(a): v for a, v in new["harvest"].items()}
    hv_old = {int(a) for a in old["harvest"]}
    contaminated = set()
    for l in open(NEW / "blue_reports.jsonl"):
        b = json.loads(l)
        if b.get("act") in ("lead", "watch", "siblings", "scan"):
            for k in ("account", "accounts", "ids"):
                v = b.get(k)
                for x in (v if isinstance(v, list) else [v]):
                    if isinstance(x, int):
                        contaminated.add(x)
    ring = {int(a) for a in new["labels"]}
    labels = {int(a): c for a, c in new["labels"].items()}
    rows = json.load(open(NEW / "blue_fleets.json"))["rows"]
    fleet = F.fleets_from_rows([(i, t) for i, t in rows])
    created = {}
    for l in open(sorted(D.glob("census-2026*.jsonl"))[-1]):
        r = json.loads(l)
        if r.get("created_at"):
            created[r["account_id"]] = T(r["created_at"])
    return hv_new, hv_old, contaminated - set(hv_new), ring, labels, fleet, created


def sixgrams(text):
    w = detect.words(text)
    return {" ".join(w[i:i + 6]) for i in range(max(0, len(w) - 5))}


def main():
    posts, vecs, ids, acc, ts, by = load()
    hv_new, hv_old, contaminated, ring, labels, fleet, created = blue_labels()
    print(f"{len(posts)} posts, {len(by)} accounts; harvest {len(hv_new)} (old {len(hv_old)}), ring accounts {len(ring)}, "
          f"contaminated negatives dropped {len(contaminated)}")

    mu = vecs.mean(0)
    C = vecs - mu
    C /= np.linalg.norm(C, axis=1, keepdims=True) + 1e-9
    km = MiniBatchKMeans(n_clusters=12, random_state=0, n_init=3).fit(C[RNG.choice(len(C), min(60000, len(C)), replace=False)])
    theme = km.predict(C)

    texts = [p["x"] for p in posts]
    tf = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, max_features=300000, sublinear_tf=True, dtype=np.float32)
    TF = tf.fit_transform(texts)

    src = detect.source_hashes()
    gram_acc = collections.defaultdict(set)
    post_grams = {}
    for i, t in enumerate(texts):
        g = {x for x in sixgrams(t) if detect.h(x) not in src}
        post_grams[i] = g
        for x in g:
            gram_acc[x].add(int(acc[i]))

    # the live fingerprint rule (detect.py): one 6-word sequence from FP_ACCOUNTS+ accounts inside 24 h
    gram_times = collections.defaultdict(list)
    for i, g in post_grams.items():
        for x in g:
            if len(gram_acc[x]) >= detect.FP_ACCOUNTS:
                gram_times[x].append((ts[i], int(acc[i])))
    for v in gram_times.values():
        v.sort()

    def fingerprint(a, grams_of_account, t_end):
        for x in grams_of_account:
            v = gram_times.get(x)
            if v and len({b for t, b in v if t_end - 86400 <= t <= t_end}) >= detect.FP_ACCOUNTS:
                return True
        return False

    # whole-history centroids of every account: who looks like whom
    cent_ids = [a for a, ix in by.items() if len(ix) >= K_MIN]
    M = np.stack([C[by[a]].mean(0) for a in cent_ids])
    M /= np.linalg.norm(M, axis=1, keepdims=True) + 1e-9
    pos_of = {a: j for j, a in enumerate(cent_ids)}

    # ---------- Q1: build examples with cutoffs ----------
    pos_cut = {}
    for a, v in hv_new.items():
        if a in by:
            pos_cut[a] = v["hidden_post"]
    cut_pool = np.array(sorted(pos_cut.values()))
    examples = []                                       # (account, cutoff id, label)
    for a, c in pos_cut.items():
        examples.append((a, c, 1))
    negs = [a for a in by if a not in hv_new and a not in contaminated]
    for a in negs:
        for _ in range(30):
            c = int(RNG.choice(cut_pool))
            if (ids[by[a]] < c).sum() >= K_MIN:
                examples.append((a, c, 0))
                break

    rows, kept = [], []
    for a, c, y in examples:
        ring_posts = set(hv_new.get(a, {}).get("ring_posts", [])) if y else set()
        ix = [i for i in by[a] if ids[i] < c and ids[i] not in ring_posts][-WINDOW:]
        if len(ix) < K_MIN:
            continue
        ix = np.array(ix)
        X = C[ix]
        S = X @ X.T
        n = len(ix)
        off = (S.sum() - np.trace(S)) / (n * (n - 1))
        R = vecs[ix] @ vecs[ix].T
        np.fill_diagonal(R, 0)
        nd = float((R.max(1) >= NEARDUP).mean())
        cent = X.mean(0)
        cn = float(np.linalg.norm(cent))
        cent /= np.linalg.norm(cent) + 1e-9
        sims = M @ cent
        if a in pos_of:
            sims[pos_of[a]] = -1
        th = np.bincount(theme[ix], minlength=12) / n
        ent = float(-(th[th > 0] * np.log(th[th > 0])).sum() / np.log(12))
        # lexical baselines
        Tm = TF[ix]
        L = (Tm @ Tm.T).toarray()
        lex = (L.sum() - np.trace(L)) / (n * (n - 1))
        own = collections.Counter(x for i in ix for x in post_grams[i])
        rep = float(np.mean([any(own[x] > 1 for x in post_grams[i]) for i in ix]))
        others = set()
        for x in own:
            others |= gram_acc[x]
        others.discard(a)
        # behaviour
        t = ts[ix]
        span = max((t.max() - t.min()) / 3600, 1.0)
        last24 = t[t >= t.max() - 86400]
        hrs = len({int(x // 3600) for x in last24})
        gaps = np.diff(np.sort(t))
        txt = [texts[i] for i in ix]
        side_y = np.mean([bool(YES.search(s)) for s in txt])
        side_n = np.mean([bool(NO.search(s)) for s in txt])
        age = (t.max() - created.get(a, t.min())) / 3600
        rows.append(dict(
            beh=[n, np.mean([posts[i]["k"] == "reply" for i in ix]), n / span, np.log1p(max(age, 0)), np.median(gaps) if len(gaps) else 0,
                 np.mean([len(s) for s in txt]), np.mean(["#" in s for s in txt]), side_y, side_n],
            lex=[lex, rep, np.log1p(len(others))],
            emb=[off, nd, float(sims.max()), np.log1p(int((sims >= LOOKALIKE).sum())), ent, cn],
            flag=int(fingerprint(a, own, float(t.max())) or (hrs >= 20 and n >= 40) or (len(last24) >= 20 and span <= 1.0)),
        ))
        kept.append((a, c, y))
    y = np.array([k[2] for k in kept])
    grp = np.array([hash(fleet.get(k[0], f"a{k[0]}")) % (2**31) for k in kept])
    names = {k: np.array([r[k] for r in rows], dtype=float) for k in ("beh", "lex", "emb")}
    flag = np.array([r["flag"] for r in rows])
    isring = np.array([k[0] in ring for k in kept])
    print(f"Q1 examples: {len(y)} ({int(y.sum())} positive); negatives in a Blue cluster: {int((isring & (y == 0)).sum())}")

    def cv(Xm, yy, gg, seeds=5):
        oof = np.zeros((seeds, len(yy)))
        for s in range(seeds):
            for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=s).split(Xm, yy, gg):
                sc = StandardScaler().fit(Xm[tr])
                m = LogisticRegression(C=0.5, class_weight="balanced", max_iter=2000).fit(sc.transform(Xm[tr]), yy[tr])
                oof[s, te] = m.decision_function(sc.transform(Xm[te]))
        return oof

    def auc_of(oof, yy):
        return float(np.mean([roc_auc_score(yy, o) for o in oof]))

    def boot_delta(a, b, yy, n=500):
        ma, mb = a.mean(0), b.mean(0)
        out = []
        for _ in range(n):
            ix = RNG.integers(0, len(yy), len(yy))
            if yy[ix].min() == yy[ix].max():
                continue
            out.append(roc_auc_score(yy[ix], mb[ix]) - roc_auc_score(yy[ix], ma[ix]))
        return float(np.mean(out)), float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))

    sets = {
        "behaviour": ["beh"], "lexical": ["lex"], "embedding": ["emb"],
        "behaviour+lexical": ["beh", "lex"], "behaviour+lexical+embedding": ["beh", "lex", "emb"],
    }
    res = {"n": int(len(y)), "pos": int(y.sum())}

    def run(mask, tag):
        out, oofs = {}, {}
        for nm, parts in sets.items():
            Xm = np.hstack([names[p][mask] for p in parts])
            oofs[nm] = cv(Xm, y[mask], grp[mask])
            out[nm] = auc_of(oofs[nm], y[mask])
        d = boot_delta(oofs["behaviour+lexical"], oofs["behaviour+lexical+embedding"], y[mask])
        out["delta_emb_over_beh_lex"] = d
        mm = oofs["behaviour+lexical+embedding"].mean(0)
        mb = oofs["behaviour+lexical"].mean(0)
        yy, ff = y[mask], flag[mask]
        for K in (50, 100):
            out[f"precision@{K}"] = dict(emb=float(yy[np.argsort(-mm)[:K]].mean()), beh_lex=float(yy[np.argsort(-mb)[:K]].mean()), base=float(yy.mean()))
        miss = (yy == 1) & (ff == 0)
        top = int(0.1 * len(yy))
        out["current_detector"] = dict(flagged_pos=int(((yy == 1) & (ff == 1)).sum()), flagged_neg=int(((yy == 0) & (ff == 1)).sum()), pos=int(yy.sum()))
        out["recall_of_unflagged_positives_in_top10pct"] = dict(
            emb=float(np.isin(np.where(miss)[0], np.argsort(-mm)[:top]).mean()) if miss.any() else None,
            beh_lex=float(np.isin(np.where(miss)[0], np.argsort(-mb)[:top]).mean()) if miss.any() else None)
        res[tag] = out
        print(tag, json.dumps(out, indent=1))

    run(np.ones(len(y), bool), "all_negatives")
    run((y == 1) | isring, "ring_negatives_only")

    # permutation control: shuffle labels by group, same pipeline (full feature set)
    Xf = np.hstack([names[p] for p in ("beh", "lex", "emb")])
    perm = []
    for s in range(10):
        yp = y.copy()
        RNG.shuffle(yp)
        perm.append(float(np.mean([roc_auc_score(yp, o) for o in cv(Xf, yp, grp, seeds=1)])))
    res["permutation_auc"] = dict(mean=float(np.mean(perm)), max=float(np.max(perm)))
    print("permutation AUC", res["permutation_auc"])

    # hold-out: train on the old harvest, test on positives found after it (and their fleets)
    newonly = np.array([k[0] not in hv_old and k[2] == 1 for k in kept])
    test_groups = set(grp[newonly]) | set(RNG.choice(np.unique(grp), len(np.unique(grp)) // 4, replace=False))
    te = np.isin(grp, list(test_groups))
    tr = ~te & ~newonly
    hold = {"train": int(tr.sum()), "test": int(te.sum()), "test_pos": int(y[te].sum())}
    for nm, parts in (("behaviour+lexical", ["beh", "lex"]), ("behaviour+lexical+embedding", ["beh", "lex", "emb"])):
        Xm = np.hstack([names[p] for p in parts])
        sc = StandardScaler().fit(Xm[tr])
        m = LogisticRegression(C=0.5, class_weight="balanced", max_iter=2000).fit(sc.transform(Xm[tr]), y[tr])
        hold[nm] = float(roc_auc_score(y[te], m.decision_function(sc.transform(Xm[te])))) if y[te].min() != y[te].max() else None
    res["holdout"] = hold
    print("holdout", hold)

    # ---------- Q2: does text carry team identity? ----------
    members = collections.defaultdict(list)
    for a in cent_ids:
        if a in fleet:
            members[fleet[a]].append(a)
    big = [m for m in members.values() if len(m) >= 5]
    same, diff = [], []
    for m in big:
        idx = [pos_of[a] for a in m]
        S = M[idx] @ M[idx].T
        same.extend(S[np.triu_indices(len(idx), 1)])
    allidx = np.arange(len(cent_ids))
    fl = np.array([fleet.get(a, "") for a in cent_ids])
    for _ in range(len(same)):
        i, j = RNG.choice(allidx, 2, replace=False)
        if fl[i] != fl[j] or fl[i] == "":
            diff.append(float(M[i] @ M[j]))
    yy = np.r_[np.ones(len(same)), np.zeros(len(diff))]
    res["q2_fleet_pairs"] = dict(fleets=len(big), same_pairs=len(same), auc=float(roc_auc_score(yy, np.r_[same, diff])),
                                 mean_same=float(np.mean(same)), mean_diff=float(np.mean(diff)))
    print("Q2 same-fleet vs different-fleet centroid cosine", res["q2_fleet_pairs"])

    # cross-fleet look-alikes vs Blue cluster and fate
    last = {}
    for a, ix in by.items():
        last[a] = ts[ix].max()
    now = max(last.values())
    dead = {a: (now - last[a]) > 24 * 3600 for a in by}
    Q = M @ M.T
    np.fill_diagonal(Q, -1)
    iu = np.triu_indices(len(cent_ids), 1)
    cross = np.array([fl[i] != fl[j] or fl[i] == "" for i, j in zip(*iu)])
    sims = Q[iu]
    lab = np.array([labels.get(a, "") for a in cent_ids])
    dd = np.array([dead.get(a, False) for a in cent_ids])
    out = []
    for q in (0.999, 0.9999):
        thr = np.quantile(sims[cross], q)
        sel = cross & (sims >= thr)
        ii, jj = iu[0][sel], iu[1][sel]
        lab_ok = (lab[ii] != "") & (lab[jj] != "")
        base = RNG.integers(0, len(cent_ids), (200000, 2))
        base = base[(lab[base[:, 0]] != "") & (lab[base[:, 1]] != "") & (base[:, 0] != base[:, 1])]
        out.append(dict(quantile=q, threshold=float(thr), pairs=int(sel.sum()),
                        same_label=float((lab[ii] == lab[jj])[lab_ok].mean()) if lab_ok.any() else None,
                        same_label_random=float((lab[base[:, 0]] == lab[base[:, 1]]).mean()),
                        same_fate=float((dd[ii] == dd[jj]).mean()), same_fate_random=float((dd[RNG.integers(0, len(dd), 100000)] == dd[RNG.integers(0, len(dd), 100000)]).mean())))
    res["q2_cross_fleet"] = out
    print("Q2 cross-fleet look-alikes", json.dumps(out, indent=1))

    # our own team: do our 30 voices find each other among the rivals?
    ours_f = D / "ours.jsonl"
    if ours_f.exists():
        from fastembed import TextEmbedding
        model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
        ov = []
        for l in open(ours_f):
            r = json.loads(l)
            tx = [re.sub(r"\s+", " ", re.sub(r"https?://\S+|@\w+", " ", p["b"])).strip() for p in r["posts"] if p["k"] != "repost" and p.get("b")]
            tx = [s for s in tx if len(s) >= 20]
            if len(tx) >= K_MIN:
                v = np.array(list(model.embed(tx, batch_size=128)), dtype=np.float32)
                v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-9
                c = v - mu
                c /= np.linalg.norm(c, axis=1, keepdims=True) + 1e-9
                m = c.mean(0)
                ov.append(m / (np.linalg.norm(m) + 1e-9))
        if len(ov) >= 5:
            ov = np.stack(ov)
            same = (ov @ ov.T)[np.triu_indices(len(ov), 1)]
            rival = ov @ M.T
            yy = np.r_[np.ones(len(same)), np.zeros(rival.size)]
            res["q2_ours"] = dict(voices=len(ov), same_pairs=len(same), auc_ours_vs_rivals=float(roc_auc_score(yy, np.r_[same, rival.ravel()])),
                                  mean_same=float(same.mean()), mean_voice_rival=float(rival.mean()))
            # the same, for an arbitrary rival fleet of similar size, as a yardstick
            print("Q2 our voices", res["q2_ours"])

    json.dump(res, open(E / "results.json", "w"), indent=1)


if __name__ == "__main__":
    main()
