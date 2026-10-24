#!/usr/bin/env python
"""Post-hoc follow-up to blue_embed_eval.py Q2 (not in the pre-declared rules): how far do text look-alikes reach, and
do they over-merge? Local files only.

Links two accounts when their topic-centred centroid cosine is at least THR. Reports the groups that result: how many
fleets they join, group sizes (a team holds at most 200 accounts), and fate / Blue-cluster agreement inside groups.

    python scripts/blue_embed_links.py [THR ...]      # default 0.86 0.92
"""
import collections
import json
import sys

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

sys.path.insert(0, "scripts")
import blue_embed_eval as ev  # noqa: E402

K_MIN = 10


def main():
    thrs = [float(x) for x in sys.argv[1:]] or [0.86, 0.92]
    posts, vecs, ids, acc, ts, by = ev.load()
    hv_new, hv_old, contaminated, ring, labels, fleet, created = ev.blue_labels()
    mu = vecs.mean(0)
    C = vecs - mu
    C /= np.linalg.norm(C, axis=1, keepdims=True) + 1e-9
    accts = [a for a, ix in by.items() if len(ix) >= K_MIN]
    M = np.stack([C[by[a]].mean(0) for a in accts])
    M /= np.linalg.norm(M, axis=1, keepdims=True) + 1e-9
    now = max(ts[by[a]].max() for a in accts)
    dead = np.array([(now - ts[by[a]].max()) > 86400 for a in accts])
    fl = np.array([fleet.get(a, f"a{a}") for a in accts])
    lab = np.array([labels.get(a, "") for a in accts])
    hid = np.array([a in hv_new for a in accts])
    S = M @ M.T
    np.fill_diagonal(S, -1)
    print(f"{len(accts)} accounts with {K_MIN}+ texts; fleets {len(set(fl))}")
    for thr in thrs:
        A = csr_matrix(S >= thr)
        n, comp = connected_components(A, directed=False)
        sizes = collections.Counter(comp)
        multi = [c for c, s in sizes.items() if s >= 2]
        in_group = sum(sizes[c] for c in multi)
        fleets_per = [len(set(fl[comp == c])) for c in multi]
        big = sorted(((sizes[c], len(set(fl[comp == c]))) for c in multi), reverse=True)[:8]
        over200 = sum(1 for c in multi if sizes[c] > 200)
        agree_f, agree_l = [], []
        for c in multi:
            ix = np.where(comp == c)[0]
            if len(ix) > 400:
                ix = np.random.default_rng(0).choice(ix, 400, replace=False)
            d = dead[ix]
            p = len(ix) * (len(ix) - 1) / 2
            nd = d.sum()
            agree_f.append(((nd * (nd - 1) + (len(ix) - nd) * (len(ix) - nd - 1)) / 2, p))
            lb = [x for x in lab[ix] if x]
            if len(lb) > 1:
                cnt = collections.Counter(lb)
                agree_l.append((sum(v * (v - 1) / 2 for v in cnt.values()), len(lb) * (len(lb) - 1) / 2))
        print(f"\nTHR {thr}: {in_group} accounts ({in_group / len(accts):.0%}) sit in {len(multi)} groups; "
              f"fleets per group median {int(np.median(fleets_per))}, max {max(fleets_per)}; groups over 200 accounts: {over200}")
        print("  biggest groups (accounts, fleets):", big)
        print(f"  same fate inside groups: {sum(a for a, _ in agree_f) / sum(p for _, p in agree_f):.0%} of pairs "
              f"(random {dead.mean() ** 2 + (1 - dead.mean()) ** 2:.0%})")
        if agree_l:
            print(f"  same Blue cluster inside groups: {sum(a for a, _ in agree_l) / sum(p for _, p in agree_l):.0%} of labelled pairs")
        print(f"  accounts with a hidden post: {int(hid.sum())} overall; in groups {int(hid[np.isin(comp, multi)].sum())}")


if __name__ == "__main__":
    main()
