# 07: Blue desk: report the ring bots (fastest catch-up)

**Owner:** Blue lead · **Depends on:** nothing for v0 (08 makes it better) · **When:** start **today**

## Why
- Organisers, 20 Oct: the pending-report cap went 20 → **25**, and the automoderation base timer 24 h → 6 h → **3 h**. "If you're wondering how you might be able to catch up to the top teams, I hope that you will explore the reporting mechanics more! Every team only gets a finite number of bots."
- Estimate: ~60–120 paid reports/day × 25 ≈ **1,500–3,000 Blue points/day**, more than our total Red so far. It also hides the ring posts that keep Yes on top of Trending ([diagnosis](../docs/06-strategy/diagnosis-2026-10-20.md#blue-track-estimate-after-the-20-oct-rule-change)).
- Rules: [scoring §3](../docs/03-scoring/scoring-guide.md#3-reporting-inauthentic-posts-and-accounts) and [api-reference: Reporting](../docs/04-technical/api-reference.md#reporting-blue-track). Record the 20 Oct changes in `scoring-guide.md` with the date, and log them in [open questions](../docs/05-reference/discrepancies-and-open-questions.md).

## The mechanics that shape the design
- **First** team to report a post that's ruled inauthentic gets 25; later reporters get 5. **Speed matters**: report fresh ring posts.
- About 1 in 4 rulings is wrong. A "genuine" ruling locks **new** reports for 6 h; pending ones still resolve. So keep the 25 pending slots full with the **highest-confidence** targets, and expect a lock now and then.
- Per target team per day: 5 full, 5 half, then 10%. Spread reports across **many teams**. We can't see team ids, so we use **clusters** as a proxy (below).
- Account reports (15 each to every reporter) only succeed if the account already has ≥1 permanently hidden post and ≥100 actions. Ring likers easily pass 100 actions. So: post report first; once it's ruled hidden, account report.
- Never report citizens, verified accounts (ids 1–11) or our own accounts. Report on **evidence of automation**, not on side or team (rules §5.2.2; LS.6.5 bans bad-faith reporting).

## How to find targets (all read-only)
Evidence classes, strongest first:
1. **Reply ring on one post:** 20+ team replies within minutes, one persona each, all the same frame, roughly one a minute (e.g. post 58923: 66 team replies, all hospital angles; ids 3089–5649).
2. **Like ring:** 40–90 team likes, almost no citizen likes, within the first 30 min (e.g. 63081, 62601, 63465, 63779, 34 of which got 0 citizen likes).
3. **Burst-registered families:** accounts created within the same minute with templated usernames (e.g. `zoe.scott06`, `samuel.king81`, `chloe.young27`, all 07:07 on 19 Oct and all liking the same posts).
4. **Leaked LLM text**, duplicate bodies, empty bodies.

**Cluster** accounts by co-liking and co-replying (a Jaccard over the post sets they touched). One cluster ≈ one team. That gives us the per-team diminishing-rate proxy: about 5 reports per cluster per Sydney day.

## Build (v0 today, by hand + script; v1 automated)
- **v0 (today):** `scripts/blue_candidates.py`, read-only. Scan Trending + Latest, score posts on evidence 1–3, print the top 25 with the evidence sentence. A human reads each and files it from one of our accounts with `report_post(post_id, "inauthentic", "I think that this content is inauthentic (bot) activity because <evidence>")`. The detail must be specific (counts, timing, account ages). Log every report to `logs/blue_reports.jsonl` with owner, target, evidence, and later the ruling.
- **v1:** a `blue` job type in the writer's process (it uses the report budgets, 3/min each, separate from posting). It auto-files only above a confidence threshold, keeps ≤ 25 pending, and caps per cluster per day. It reads rulings back (watch whether the post becomes hidden) and computes our precision. If precision drops below ~70%, it drops back to human approval.
- **Protect ourselves:** the same detector runs on **our own** accounts. If we start looking like evidence 1–3 (after 04), we'll be reported the same way.

## Done when
v0: 25 pending reports filed today with logged evidence. v1: precision measured over ≥ 50 rulings, auto-filing on, reports spread over ≥ 10 clusters per day.
