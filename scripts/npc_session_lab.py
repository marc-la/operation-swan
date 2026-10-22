"""Composable session lab. A cell is a tuple of parts; each part adds items to the citizen's session.
python3 lab.py prep <round> <drafts.json> <cells>   ->  <round>_batch<k>.json, <round>_key.json
python3 lab.py score <round>
Parts: like, follow, repost_them, peer, own_post, reply:<field>, reply2:<field>  (field: sent or a drafts key)."""
import json, random, sys, pathlib, statistics as st, collections
D = pathlib.Path(__file__).parent
FILL = ["ferry_watch: 7:40 sailing running 15 min late again, bring a coat",
        "kingston_bakes: sourdough's back on the shelf from tomorrow",
        "reefside_fc: under-12s won 3-1 on saturday, proud of the lot of them",
        "tide_tables_ks: king tide sunday morning, harbour car park may flood",
        "ana_gardens: the frangipani on Beach Rd is out, worth the walk",
        "kingstonia_libs: school holiday craft sessions start monday"]
PEER = ["exactly. you can't fix a bad question with a yes and hope for the best.",
        "that's the problem, we're voting on a massive change without any of the specifics or a way to wind it back",
        "couldve at least put a draft out. voting no on this isnt the same as voting against the vaccine.",
        "a yes vote right now would be giving them a permanent tool without any built-in way to turn it off",
        "it'll get dumped on whoever's at the counter. if they want rules, publish the venue list and sort out training first."]
PEERNAME = ["mere_t", "jonah_b88", "lisi_f", "pat_kerr", "sione_v"]
ME = "isla_p"

def citizens():
    c = json.load(open(D / "cases.json"))[:12] + json.load(open(D / "leaners.json"))
    for x in c: x["seg"] = "lean_no" if x["id"].startswith("n") else "persuadable"
    return c

def session(c, i, cell, dr):
    n, home = [], []
    for part in cell:
        kind, _, field = part.partition(":")
        text = c["sent"] if field == "sent" else dr.get(c["id"], {}).get(field)
        if kind in ("reply", "reply2"): n.append(f"[notification] {ME} replied to your post: {text}")
        elif kind == "like": n.insert(0, f"[notification] {ME} liked your post")
        elif kind == "follow": n.insert(0, f"[notification] {ME} followed you")
        elif kind == "repost_them": n.insert(0, f"[notification] {ME} reposted your post")
        elif kind == "peer": home.append(f"[trending] {PEERNAME[i % 5]}: {PEER[i % 5]}  (38 likes, 7 reposts)")
        elif kind == "own_post": home.append(f"[home, an account you follow] {ME}: {dr[c['id']]['own_post']}")
    return "\n".join(n + home + [f"[home] {FILL[(i + k) % 6]}" for k in (0, 1)])

def prep(rnd, drafts, cells, per_batch=4):
    dr = json.load(open(D / drafts)); cs = citizens(); rng = random.Random(hash(rnd) % 1000)
    key, batches = {}, [[] for _ in range((len(cs) + per_batch - 1) // per_batch)]
    for i, c in enumerate(cs):
        names = list(cells); rng.shuffle(names)
        key[c["id"]] = {f"S{j+1}": nm for j, nm in enumerate(names)}
        batches[i % len(batches)].append(dict(id=c["id"], your_post=c["citizen_post"],
                                              sessions={f"S{j+1}": session(c, i, cells[nm], dr) for j, nm in enumerate(names)}))
    json.dump(dict(key=key, seg={c["id"]: c["seg"] for c in cs}), open(D / f"{rnd}_key.json", "w"))
    for b, items in enumerate(batches): json.dump(items, open(D / f"{rnd}_batch{b}.json", "w"), indent=1)
    print(len(batches), "batches")

def score(rnd):
    k = json.load(open(D / f"{rnd}_key.json")); key, seg = k["key"], k["seg"]
    R = {}
    for f in sorted(D.glob(f"{rnd}_ratings*.json")): R.update(json.load(open(f)))
    for sg in ("persuadable", "lean_no"):
        S = collections.defaultdict(lambda: collections.defaultdict(list))
        for cid, r in R.items():
            if seg[cid] != sg: continue
            b = r["baseline"]
            for lab, cell in key[cid].items():
                x = r[lab]
                for m in ("stance", "certain", "vote"):
                    S[cell][m].append(float(x[m]) - float(b[m]))
                S[cell]["mind"].append(float(x["mind"])); S[cell]["fake"].append(bool(x["fake"]))
                S[cell]["unf"].append(x.get("act") == "unfollow_or_mute")
        n = sum(seg[c] == sg for c in R)
        print(f"\n{sg} ({n} citizens)   d = change from their baseline")
        print(f"{'cell':22}{'dStance':>8}{'toYes':>6}{'dCertain':>9}{'dVote':>6}{'mind':>5}{'bots%':>6}{'mute':>5}")
        for cell, v in sorted(S.items(), key=lambda kv: -(st.mean(kv[1]['stance']) + st.mean(kv[1]['certain']) / 2)):
            print(f"{cell:22}{st.mean(v['stance']):+8.2f}{sum(x <= -0.5 for x in v['stance']):6}{st.mean(v['certain']):+9.2f}"
                  f"{st.mean(v['vote']):+6.2f}{st.mean(v['mind']):5.1f}{100*sum(v['fake'])/len(v['fake']):6.0f}{sum(v['unf']):5}")

if __name__ == "__main__":
    if sys.argv[1] == "prep":
        prep(sys.argv[2], sys.argv[3], json.loads(open(D / sys.argv[4]).read()))
    else:
        score(sys.argv[2])
