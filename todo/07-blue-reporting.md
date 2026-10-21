# 07: Blue reporting: report the ring bots

**Owner:** Blue lead · **Depends on:** nothing · **When:** live from 21 Oct

The design and the maths: [blue-reporting](../docs/06-strategy/blue-reporting.md). The rules: [scoring §3](../docs/03-scoring/scoring-guide.md#3-reporting-inauthentic-posts-and-accounts).

## Status 2026-10-21
- **Built:** `src/swan_blue` runs as its own EC2 process (`deploy/swan-blue.service`). It reports from one booster the bot no longer uses, and only touches the report routes. It scans Trending, Latest and known ring authors' timelines; it audits for like and reply rings, groups accounts into clusters, ranks candidates by expected value, and refills the 25 pending slots greedily whenever reporting isn't locked. It reads rulings back, infers locks, and harvests account reports (hidden post + ≥ 100 actions). Dashboard: the **Blue** section. Tests: `tests/test_blue.py`.
- **Dry run on live data, 21 Oct:** 39 team posts read, 21 with ring evidence, 5 clusters. The top 25 spread at most 5 per cluster. Typical: 18–23 replies from as many new accounts within 15–35 min, with 30–49 likes, all from new accounts.
- **Starts in approve mode:** posts are filed only after someone approves them (`ssh swan-ec2 'ctn/scripts/blue.sh approve all'`). It goes auto after 10 post rulings at ≥ 70% inauthentic, and back to approve below that.
- **Live 2026-10-21 13:30 UTC** (`637fa8a`): approve mode, reporter `salote_sails`, 25 reports waiting at start.
- Lost to Blue by others so far: @lani_wharfcafe23 (suspended 20 Oct); @mere_t_nana70 has 1 hidden post (21 Oct 11:02 UTC, 210 actions: one account report away from suspension).
- Expected: about 1,200 Blue points a day if slots are refilled around the clock ([model](../docs/06-strategy/blue-reporting.md#2-what-follows-from-them)).

## Left to do
- [ ] Approve the first batch (dashboard), then watch the first rulings: 404 = hidden; a lock shows on the dashboard.
- [ ] After the first lock: check what the refused report said (`logs/blue_reports.jsonl`, `"act": "refused"`) and whether the lock length matches 6 h.
- [ ] From the portal points log: what share of our hidden posts paid 25 against 5. Tune `evidence.p_first`.
- [ ] Ask `#questions` B.10 (which day an award counts on) and B.11 (do account reports count toward the 25 cap) ([open questions](../docs/05-reference/discrepancies-and-open-questions.md)).

## Done when
Precision measured over ≥ 50 rulings, auto mode on, reports spread over ≥ 10 clusters a day, and Blue points visible in the portal log every day.
