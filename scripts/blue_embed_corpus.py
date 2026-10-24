#!/usr/bin/env python
"""Offline corpus + embeddings for the Blue embedding investigation (read-only; local files only, no network except the
one-off download of the public embedding model weights; nothing is posted).

Merges every pull in data/rival_census/ (pilot, rest, leads, deep, snap*), keeps each team post's text once, strips
links and @mentions, embeds the texts with a small local sentence model and caches the result in data/embed/.

    python scripts/blue_embed_corpus.py

Writes data/embed/posts.jsonl (id, account, t, kind, text) and data/embed/vecs.npy (float16, one row per line of
posts.jsonl, unit length). Our own accounts (ours_all.json) are left out, and so are citizens and organisers (ids <= 2343).
"""
import glob
import json
import pathlib
import re

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
D = ROOT / "data" / "rival_census"
OUT = ROOT / "data" / "embed"
CITIZEN_MAX_ID = 2343
MODEL = "sentence-transformers/all-MiniLM-L6-v2"
STRIP = re.compile(r"https?://\S+|@\w+")


def clean(text):
    return re.sub(r"\s+", " ", STRIP.sub(" ", text or "")).strip()


def pull_files():
    names = ["pilot", "rest", "leads", "deep"]
    files = [D / f"{n}.jsonl" for n in names] + [pathlib.Path(p) for p in sorted(glob.glob(str(D / "snap*.jsonl")))]
    return [f for f in files if f.exists()]


def main():
    ours = {a for v in json.load(open(D / "ours_all.json")).values() for a, _ in v}
    posts = {}
    for f in pull_files():
        for line in open(f):
            r = json.loads(line)
            a = r["account_id"]
            if r.get("err") or a <= CITIZEN_MAX_ID or a in ours:
                continue
            for p in r["posts"]:
                if p["k"] == "repost" or not p.get("b"):
                    continue
                text = clean(p["b"])
                if len(text) >= 20:
                    posts[p["id"]] = (p["id"], a, p["t"], p["k"], text)
    rows = sorted(posts.values())
    print(f"{len(rows)} posts from {len({r[1] for r in rows})} accounts")
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "posts.jsonl", "w") as fh:
        for pid, a, t, k, text in rows:
            fh.write(json.dumps(dict(id=pid, a=a, t=t, k=k, x=text)) + "\n")
    from fastembed import TextEmbedding
    model = TextEmbedding(MODEL)
    vecs = np.zeros((len(rows), 384), dtype=np.float16)
    batch = 4096
    for i in range(0, len(rows), batch):
        v = np.array(list(model.embed([r[4] for r in rows[i:i + batch]], batch_size=128)), dtype=np.float32)
        v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-9
        vecs[i:i + batch] = v
        print(f"{min(i + batch, len(rows))}/{len(rows)}", flush=True)
    np.save(OUT / "vecs.npy", vecs)


if __name__ == "__main__":
    main()
