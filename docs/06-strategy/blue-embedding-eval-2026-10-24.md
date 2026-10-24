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
(filled in below once run)
