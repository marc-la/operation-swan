# Blue: do text embeddings help? Offline evaluation (24 Oct 2026)

Question (Marc, 24 Oct): can an account's posts, embedded as vectors and aggregated, help Blue find accounts worth reporting, or link fleets into teams? Read-only, local, nothing posted. Code: `scripts/blue_embed_corpus.py`, `scripts/blue_embed_eval.py` (outputs in `data/embed/`, gitignored).

## Pre-declared rules (written before any result was computed)

**Data.** Every pull in `data/rival_census/` up to the 24 Oct 14:37 UTC snapshot; Blue's state and log copied from the box at 15:31 UTC on 24 Oct (`box-0124/`). Our own accounts, citizens and organisers (ids up to 2343) are excluded.

**Q1: does it predict a hidden post?**
- Positive: an account in Blue's `harvest` (a moderator-hidden post). Features come only from the account's posts made before that hidden post (the newest 40, at least 10), minus the ring posts.
- Negative: any other readable team account, with a cutoff drawn at random from the positives' cutoffs, minus accounts Blue flagged in any lead, watch, sibling or scan record without a confirmed hide. A second run uses only negatives that sit in a Blue cluster (ring participants), the same population the positives come from.
- Features, fixed in advance. Embedding (all-MiniLM-L6-v2, topic mean removed): mean pairwise cosine, share of posts with a near-duplicate (raw cosine ≥ 0.85), nearest other-account centroid cosine, number of accounts with centroid cosine ≥ 0.85, theme entropy (12 k-means themes), centroid norm. Baselines: behaviour (post count, reply share, pace, age, median gap, length, hashtag rate, yes/no wording) and lexical (character n-gram dispersion, own 6-word repeats, accounts sharing a 6-word sequence).
- Model: logistic regression, 5-fold folds grouped by registration fleet (so fleet-mates never straddle a split), 5 seeds.
- **Pass:** adding the embedding block to behaviour + lexical lifts AUC by at least 0.05 with the 95% bootstrap interval above zero, in both the all-negatives and ring-negatives runs; and it holds on the hold-out (train on harvest as of the 23 Oct 23:23 UTC copy, test on accounts harvested after, with their fleets kept out of training). A permutation control (shuffled labels) must sit near 0.5.
- Also reported, no pass bar: precision at the top 50 and 100, and how many positives the current detector rules would not have flagged that the model ranks in its top 10%.

**Q2: does text carry team identity?**
- Same-fleet pairs (fleets of 5+) against different-fleet pairs, by centroid cosine (AUC).
- Cross-fleet look-alike pairs (top 0.1% and 0.01% of cosine) against random pairs: share in the same Blue cluster, share with the same fate (dead = no post for 24 h).
- Our 30 voices against the rival accounts (AUC).
- **Pass for fleet-merging:** same-fleet AUC ≥ 0.8, cross-fleet look-alikes ≥ 10 points above random on same cluster, and our own voices AUC ≥ 0.8. Anything less: shelve.

**Not done here:** replay on the award log (needs the passes above first); the Qwen-likelihood fingerprint; survival.

## Known weaknesses (before looking)
- Positives are accounts Blue's scanner reached (ring posts, others' hides), so selection is not random; the ring-negatives run is the check.
- Negatives are "no hide seen yet", not "never hidden"; contamination makes AUCs lower bounds.
- Blue's cluster labels over-merge (one cluster holds about 450 accounts), so they are a weak team check.
- Most accounts have only their newest 100 posts.

## Results
Run 24 Oct (data to the 14:37 UTC snapshot; 196,670 posts from 6,431 accounts). A dry run on random vectors first gave embedding gain 0.00, permutation AUC 0.50 and same-fleet AUC 0.50, so the pipeline does not invent signal.

### Q1: no. Embeddings add nothing to hide prediction (fails the rule)

2,489 examples (261 positives). AUC under fleet-grouped 5-fold, 5 seeds:

| Feature set | All negatives | Ring-cluster negatives only |
|---|---|---|
| Behaviour | 0.700 | 0.685 |
| Lexical | 0.579 | 0.529 |
| Embedding alone | 0.616 | 0.570 |
| Behaviour + lexical | 0.726 | 0.717 |
| Behaviour + lexical + embedding | 0.725 | 0.703 |
| Gain from embedding (95% interval) | +0.002 (-0.012, +0.016) | -0.012 (-0.022, -0.004) |

Hold-out (train on the 23 Oct harvest, test on later positives and their fleets, 145 test positives): 0.687 without embedding, 0.685 with. Permutation control 0.49. Precision at the top 100 is no better with embeddings (0.36 against 0.43 all-negatives; 0.56 against 0.55 ring-only). Embedding alone beats chance (0.62), but whatever it knows, behaviour and lexical features already know.

The comparison with the current detector rules did not work: my stand-in for the fingerprint rule flagged 259 of 261 positives and also 2,036 of 2,228 negatives (91%), so it separates nothing and "positives it misses" is two accounts. Either the corpus is full of shared 6-word phrases or my version is looser than the live one (which samples 1 in 4 sequences). Not a finding about the live detector.

### Q2: text does carry team identity, but not enough for the bar; its tail is strong

- Same-fleet against different-fleet pairs (fleets of 5+): AUC **0.70** (mean cosine 0.28 against 0.00). **Fails the 0.8 bar.** Many fleets are not one voice.
- Cross-fleet look-alikes (top 0.1% of pairs, cosine 0.86+; 3,880 pairs): **81%** share a Blue cluster (random 10%) and **81%** share a fate (random 52%). Top 0.01%: 83% and 85%. **Passes the +10 points bar by a wide margin.**
- Our 30 voices against rivals: AUC **0.99**, mean pairwise cosine 0.64. **Passes.**
- By the rule written above (all three needed) fleet-merging is **not passed**. What follows is post-hoc, with `scripts/blue_embed_links.py`: linking accounts at centroid cosine 0.86+ puts 913 of 2,798 accounts (33%) into 117 groups (median 2 fleets, up to 23; none over a team's 200; 78% same fate inside groups against 51%; 69% same Blue cluster). At 0.92: 15% of accounts, 54 groups, 86% same fate. Groups hold hidden-post accounts at the same rate as everyone (84 of 292 against 33%), so grouping finds teams, not hide risk.

### What this does and does not support
- Do not add an embedding detector for account leads (Q1).
- A text link between fleets is a high-precision, low-recall way to say "these fleets are probably one team" for the per-team award count (blue-reporting §10: 46% of 24 Oct awards paid reduced). Whether it would have prevented those reduced awards is **untested**: it needs a replay on the award log (for each report, would the target's text group already have had 5 awards?).
- Our voices are far more alike than a typical rival fleet (0.64 against 0.28). Not compared against rival Vote-No accounts specifically, so it may be the side's shared message; worth a side-matched check for Red.
- Not done: award-log replay, Qwen likelihood, survival.
