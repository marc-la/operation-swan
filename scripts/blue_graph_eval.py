#!/usr/bin/env python
"""Offline check: can an interaction graph tell which rival accounts belong to one team? (todo: Blue graph, Marc 26 Oct)

Why. Blue counts awards per 'target team' (5 full, 5 half, then 10%, posts and accounts together) but has no team id: it
uses registration fleets (about 15 per team) and cluster labels (c8701 holds 450 accounts). 46% of 24 Oct's awards paid
reduced and the spread caps (blue-reporting §11) hold hundreds of candidates, both because of that. Boosters like and
reply to their own team's voices, so a graph of who interacts with whom should join the fleets of one team.

Reads only local files (no network, no secrets, nothing posted): Blue's state (the audits hold each post's liker ids and
reply authors), its report log, the portal log, the fleet list, and the rival census (for who is alive).

PRE-DECLARED BAR (written before any result was computed; it passes only if all three hold):
  G1  Joins fleets: among communities of 10+ accounts, the median number of fleets per community is at least 2, and
      after splitting none is larger than a team's allowance (200).
  G2  Same team, not only same batch: for pairs of accounts (30+ posts) in one community but in different fleets, the
      same-fate share (dead = silent 24 h+, alive = under 6 h) is at least 65%, and at least 10 points above the same
      pairs with fates shuffled. (Fleets: 76%; clusters: 63.5%.)
  G3  Replay: on the days of the portal log, attributing each hidden post to its graph community predicts the number of
      post awards paid at full / half / tenth rate with at least 20% less absolute error than fleets and than labels.
If any fails, shelve it. The replay uses post awards only for the observed side (the portal names post and account
awards apart) and counts a team's account rulings as awards too (upheld or not is unknown, so it is shown both ways).

usage: python scripts/blue_graph_eval.py BOXDIR [--resolution R]
  BOXDIR holds blue_state.json, blue_reports.jsonl, portal.json, blue_fleets.json copied from the box.
"""
import argparse
import collections
import datetime as dt
import json
import pathlib
import random
import re
import sys

import networkx as nx

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from swan_blue import fleets as F  # noqa: E402
from blue_fleet_eval import fates  # noqa: E402

CITIZEN_MAX = 2343
TEAM_MAX = 200
SYD = dt.timedelta(hours=11)   # Sydney in late October (daylight saving)


def load_ours():
    ours = set()
    for lst in json.load(open(ROOT / "data/rival_census/ours_all.json")).values():
        ours |= {a[0] if isinstance(a, list) else a for a in lst}
    return ours


def build_graph(state, ours):
    """Weighted graph of team accounts: an edge between a post's author and each account that liked or replied to it."""
    g = nx.Graph()
    n_posts = 0
    for v in state["posts"].values():
        a = v.get("audit")
        if not a:
            continue
        au = int(a["author"])
        if au <= CITIZEN_MAX or au in ours:
            continue
        n_posts += 1
        others = {int(x) for x in a.get("liker_ids", [])}
        others |= {int(r["author"]) for r in a.get("reply_posts", [])}
        for x in others:
            if x != au and x > CITIZEN_MAX and x not in ours:
                w = g[au][x]["weight"] + 1 if g.has_edge(au, x) else 1
                g.add_edge(au, x, weight=w)
    return g, n_posts


def split(g, nodes, res, seed):
    """Louvain on the subgraph, then again at a higher resolution on any community over a team's allowance."""
    sub = g.subgraph(nodes)
    out = []
    for c in nx.community.louvain_communities(sub, weight="weight", resolution=res, seed=seed):
        if len(c) > TEAM_MAX and res < 20:
            out += split(g, c, res * 2, seed)
        else:
            out.append(set(c))
    return out


def communities(g, res, seed=1):
    out = []
    for comp in nx.connected_components(g):
        out += split(g, comp, res, seed) if len(comp) > 1 else [set(comp)]
    return out


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def pairs_same_fate(groups, fate, rng, shuffles=30, cross_only=None):
    """Same-fate share over pairs inside a group (optionally only pairs in different `cross_only` units), against the
    same pairs with the fates shuffled across accounts."""
    pr = []
    for members in groups:
        m = [i for i in members if i in fate]
        for a in range(len(m)):
            for b in range(a + 1, len(m)):
                if cross_only is None or cross_only.get(m[a]) != cross_only.get(m[b]):
                    pr.append((m[a], m[b]))
    if not pr:
        return None
    obs = sum(fate[a] == fate[b] for a, b in pr) / len(pr)
    ids = list(fate)
    vals = [fate[i] for i in ids]
    base = []
    for _ in range(shuffles):
        rng.shuffle(vals)
        f = dict(zip(ids, vals))
        base.append(sum(f[a] == f[b] for a, b in pr) / len(pr))
    mu = sum(base) / len(base)
    sd = (sum((x - mu) ** 2 for x in base) / len(base)) ** 0.5 or 1e-9
    return obs, mu, (obs - mu) / sd, len(pr)


def observed_tiers(portal):
    """{sydney day: {tier: post awards}} and {hour ts: ...} from the portal log lines. Tier 1, 0.5, 0.1."""
    days = collections.defaultdict(lambda: collections.Counter())
    for e in portal["events"]:
        m = e["message"]
        t = ts(e["ts"])
        rate = 1.0
        mm = re.match(r"Moderation \(×([0-9.]+) points\): (.*)", m)
        body = m
        if mm:
            rate, body = float(mm.group(1)), mm.group(2)
        n = 0
        for x in re.findall(r"(\d+) (?:first )?inauthentic reports?", body):
            n += int(x)
        if n:
            days[(t + SYD).date().isoformat()][rate] += n
    return days


def team_of(row, how, comm, fleet_of):
    """The team a report counts against under each attribution, recomputed from the author (the log's own `team` field
    held whatever Blue used at the time, which was the label until 24 Oct). An author the scheme doesn't know falls
    back to its label."""
    lab = row.get("label")
    if how == "label":
        return lab
    if how == "fleet":
        return fleet_of.get(row.get("author"), lab)
    return comm.get(row.get("author"), fleet_of.get(row.get("author"), lab))


def replay(rows, rulings, how, comm, fleet_of, with_accounts, author_of):
    """Predicted post awards per Sydney day and tier when each hidden post counts against its team under `how`."""
    evs = []
    for r in rulings:
        if r["outcome"] == "hidden":
            row = rows.get(r["key"])
            if row:
                evs.append((r["ts"], row, "post"))
        elif with_accounts and r["outcome"] == "ruled":
            row = rows.get(r["key"])
            if row:
                evs.append((r["ts"], row, "acct"))
    evs.sort(key=lambda x: x[0])
    seen = collections.defaultdict(int)
    pred = collections.defaultdict(lambda: collections.Counter())
    for t, row, kind in evs:
        day = (ts(t) + SYD).date().isoformat()
        team = team_of(row, how, comm, fleet_of)
        seen[(day, team)] += 1
        k = seen[(day, team)]
        rate = 1.0 if k <= 5 else 0.5 if k <= 10 else 0.1
        if kind == "post":
            pred[day][rate] += 1
    return pred


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("box")
    ap.add_argument("--resolution", type=float, default=1.0)
    a = ap.parse_args()
    box = pathlib.Path(a.box)
    rng = random.Random(7)
    ours = load_ours()
    state = json.load(open(box / "blue_state.json"))
    g, n_posts = build_graph(state, ours)
    print(f"graph: {g.number_of_nodes()} accounts, {g.number_of_edges()} edges, from {n_posts} audited posts, "
          f"{nx.number_connected_components(g)} components")
    comms = communities(g, a.resolution)
    comms.sort(key=len, reverse=True)
    sizes = [len(c) for c in comms]
    print(f"communities: {len(comms)}; sizes top10 {sizes[:10]}; 10+ accounts: {sum(s >= 10 for s in sizes)}; "
          f"largest {sizes[0]}; singletons {sum(s == 1 for s in sizes)}")
    comm = {i: f"g{k}" for k, c in enumerate(comms) for i in c}

    fl = json.load(open(box / "blue_fleets.json"))
    fleet_of = F.fleets_from_rows([(i, t) for i, t in fl["rows"] if i not in ours])
    nf = collections.Counter()
    big = [c for c in comms if len(c) >= 10]
    per = [len({fleet_of.get(i) for i in c if i in fleet_of}) for c in big]
    per.sort()
    med = per[len(per) // 2] if per else 0
    print(f"G1: communities of 10+: {len(big)}, fleets per community median {med}, max {max(per) if per else 0}; "
          f"over {TEAM_MAX}: {sum(s > TEAM_MAX for s in sizes)}")

    cen = ROOT / "data/rival_census"
    for minp in (30,):
        fate, ref = fates(cen, minp, ours)
        groups = [c for c in comms if len(c) > 1]
        within = pairs_same_fate(groups, fate, rng)
        cross = pairs_same_fate(groups, fate, rng, cross_only=fleet_of)
        fgroups = collections.defaultdict(set)
        for i, f in fleet_of.items():
            fgroups[f].add(i)
        fl_res = pairs_same_fate(list(fgroups.values()), fate, rng)
        print(f"G2 ({minp}+ posts, {len(fate)} labelled): communities same-fate {within[0]:.1%} vs shuffled {within[1]:.1%} "
              f"(z {within[2]:.0f}, {within[3]} pairs)" if within else "G2: no pairs")
        if cross:
            print(f"   cross-fleet pairs only: {cross[0]:.1%} vs shuffled {cross[1]:.1%} (z {cross[2]:.0f}, {cross[3]} pairs)")
        if fl_res:
            print(f"   fleets for comparison: {fl_res[0]:.1%} vs {fl_res[1]:.1%} ({fl_res[3]} pairs)")

    rep = [json.loads(l) for l in open(box / "blue_reports.jsonl") if l.strip()]
    rows = {r["key"]: r for r in rep if r.get("act") == "report"}
    rulings = [r for r in rep if r.get("act") == "ruling"]
    obs = observed_tiers(json.load(open(box / "portal.json")))
    days = sorted(d for d in obs if d >= "2026-10-22")
    print("G3: post awards per Sydney day, observed [full/half/tenth] vs predicted by label / fleet / graph")
    for with_acc in (False, True):
        tot = {"label": 0, "fleet": 0, "graph": 0}
        print(f"  account rulings counted as awards: {with_acc}")
        pred = {h: replay(rows, rulings, h, comm, fleet_of, with_acc, None) for h in tot}
        for d in days:
            o = [obs[d][1.0], obs[d][0.5], obs[d][0.1]]
            line = f"   {d} obs {o}"
            for h in tot:
                p = [pred[h][d][1.0], pred[h][d][0.5], pred[h][d][0.1]]
                err = sum(abs(x - y) for x, y in zip(o, p))
                tot[h] += err
                line += f" | {h} {p} err {err}"
            print(line)
        print("   total abs error:", tot)


if __name__ == "__main__":
    main()
