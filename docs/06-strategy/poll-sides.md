# Which side is each team on? (Yes / No labels on the leaderboard, 27 Oct 2026)

Marc, 27 Oct: label every team on the leaderboard "(Yes)", "(No)" or "(?)" after its name. The board shows the top three, us and the #4 row while we are in the top three; a team that reaches #4 already has its label, since sides are kept for every team. (A clearance caption and a top-10 list were built and removed the same day at Marc's request.) This is for our own reading of the board only; nothing is posted or aimed at anyone.

## How a team's side is known
The platform does not publish it. A poll pays 6,000 to every eligible team on the **leading** side (3,000 to every eligible team when the poll is too close to call; Polls 2 and 3 need a score of 7,000). The portal timer already records every team's score once an hour (`data/team_scores.jsonl`), so a team whose hourly gain at the poll hour is thousands above its own recent pace was paid. We are **No**: if we were paid, the paid teams are No; if we were not, they are Yes; an eligible team that was not paid is on the other side. A too-close poll pays everyone and tells us nothing. Teams under the bar stay "(?)".

Code: `src/swan_dash/sides.py` (pure maths, no network, tests in `tests/test_sides.py`); `swan_dash/portal.py` refreshes `data/team_sides.json` on each run; the dashboard reads it. Print what the files say: `cd src && python -m swan_dash.sides`.

## What we know (27 Oct)
- **Poll 2** (counted 24 Oct 21:02 UTC, Yes 39.3 / No 34.1): the all-teams series starts later (25 Oct 04:32), so only the 1st and 3rd place scores span it. Both jumped (+6,210 and +5,068 over their pace) and we did not: **Vertex_CTN (Yes)** and **placeholder (Yes)**. Everyone else is "(?)".
- **i wanna go to china** (#1) is "(?)": it was 4th when Poll 2 landed, so no score of theirs spans it. **Poll 3 (Thu 29 Oct, about 05:00 Perth) settles it**, and fills in the top 10 as far as the eligible teams go.
- A side is never overwritten: a team that a later poll places on the other side is recorded under `conflicts` in `data/team_sides.json` and keeps its first label.

## Limits
A paid team is recognised by a jump of 3,500 or more over its median hourly gain of the last six hours; a team with a burst of its own at the poll hour could be misread, so the saved file keeps the evidence per team (`team_sides.json`, "evidence"). The 6,000 / 3,000 award sizes are from the scoring guide, and the first poll hour is read from the Sydney day of each poll.
