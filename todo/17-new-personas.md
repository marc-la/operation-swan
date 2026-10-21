# 17: New personas: replace lost voices and keep reserves

**Owner:** Narrative lead + a fresh Claude session · **Depends on:** nothing · **When:** 22 Oct

## Why
With Bedrock in, the models no longer limit how much we post (2026-10-21); the voices do. A heavy amplified post needs ~24 writes (post, 15–20 thread replies, 5–6 reposts) and each voice writes at most every 4 min. We have 11 voices, and they're running out:
- @lani_wharfcafe23 was suspended on 20 Oct (reported, one hidden post, over 100 actions).
- priya_rao_chemist71 and tomasi_ferryhand41 each have one hidden post and over 100 actions, so one account report suspends either. The bot keeps both off amplified posts (`config.HIDDEN_OFF_AMP`; `scripts/swan_watch.py`).
- More posting means more reports. Expect to lose more voices before 2 Nov, and the ×2/×4 days are when we can least afford it.

## What the code already does
- `bot.Accounts.maybe_register` registers a new voice from the first persona in `content.PERSONAS` with no account yet, one every 20–40 min. It stops at `--accounts` voices (12 in `deploy/run.sh`), at `config.MAX_ACCOUNTS` voices ever (15), and at `config.MAX_ACTIVE` accounts (48 of the platform's 50; 45 were active on 21 Oct, 34 of them boosters).
- So **a new persona in `content.PERSONAS` is registered automatically** once there is room. No persona is ever reused: a suspended voice's persona stays with its account.

## Persona ideas (pick 6, reserves from the rest)
The 11 left cover health (4), islands and fishing (3), and one each for teacher, student, trades, transport and grandparent. The gaps are below. The biggest: **the No side is led by the tourism board (KITB), and we have no tourism voice at all**. Every detail must come from [setting.md](../docs/01-competition/setting.md).

| # | Who | Gap it fills | What they bring (frames) | Watch out |
|---|---|---|---|---|
| 1 | **Dive-shop owner, Crown Harbour** (replaces Lani's small-business slot) | tourism, the No lead's own base | Bookings from Australia and NZ wobbling, COVID closures remembered, "I'm vaccinated, my customers are too" (F7 livelihoods, F12 open island) | Not a KITB spokesperson; never speak for Marina Castillo |
| 2 | **Resort housekeeper, 50s** | tourism workers, not owners | Would she need proof to clean rooms, and who checks the guests? Lost hours in 2020 (F7, F10 staff) | Keep her own experience; no invented resort names beyond setting.md |
| 3 | **Spice and fruit grower, outer village on the ring road** | agriculture, rural | Market days, the ring road, papers to sell at the market (F6 islands, F5 not here yet) | — |
| 4 | **Fintech developer, Kingstonia City** | software sector, young professional | The certificate as a system: who holds the data, when it's switched off, no end date (F2 no end, F8 powers) | Only setting.md facts about the certificate; no invented tech claims |
| 5 | **Parent of an 11-year-old** (turns 12 within months) | parents (only Mere and Grace now) | The age-12 line hits their family next year: school, the bus, netball (F13 age 12) | Children appear only as the parent describes them |
| 6 | **Netball / rugby club coach** | sport, parks, volunteers | Club nights in public parks, teenagers 12+ at training, volunteers checking papers (F13, F12) | — |
| 7 | **First-time voter, 18** | young voters; a "what I'll remember" voice | First ballot, friends split, phone-first register (F14 yes-but, F8 powers) | 18+, so a real voter; no school pupils |
| 8 | **Retired harbour-master, 70s, man** | older men (only women now) | Long memory: COVID rules that stayed longer than promised, "the sea teaches you to plan" (F2 no end, F9 parliament) | Calm, not angry; persuasion over grievance |
| 9 | **Worker back from NZ** (nurse-recruitment agreement, or seasonal) | diaspora returnees | Compares how other countries handled it (in-world only), family abroad (F12, F3 pro-vax anti-pass) | No real-world country policies stated as fact |
| 10 | **Former Yes-leaner, now No** (any job above) | the conversion story, the shape that trends ("I was leaning Yes, then…") | One concrete reason they switched, each post a step of it (F14, F5) | Every claim from setting.md; a believable, slow change |

Also add the matching identities in `targeting.IDENTITIES` (tourism, farming, tech, sport, young voter), so `messengers()` sends each new voice to citizens who share its world.

## Do
1. **Write 6 personas** in `content.PERSONAS`, in the same shape as the 12 there now (name, handle, role, frames, voice, the character and typing layers in `content.py` and `humanize.py`). Kimi K2.5 can draft them; a person reviews every line.
   - One replaces Lani's place in the mix (hospitality / small business). The others fill gaps that targeting shows: check which `targeting.IDENTITIES` have only one messenger, and who the Yes side's Trending posts speak to (health workers, parents, older people).
   - Every fact a persona uses must be in `docs/01-competition/setting.md` and pass the fact desk (todo/16). No real people, no real places outside Kingstonia.
   - Each one must sound different from the existing 11: run `tests/test_voices.py` and `tests/test_characters.py`, and add each persona there.
2. **Raise the caps for the reserve:** `--accounts` in `deploy/run.sh` to 14 and `config.MAX_ACCOUNTS` to 21 (12 used + 6 new + 3 spare). Keep `MAX_ACTIVE` at 48. If the active count is the limit, lower `--boosters` by as many as new voices are needed: likes run at ~20/min against a 30/min team limit, so 2–3 fewer boosters cost little.
3. **Owner records:** every new account is attributed to a team member in `secrets/swan_accounts.json` (`owner`), as the bot already does (CLAUDE.md rule 6).
4. Dry run (`python scripts/run_swan.py --samples 12`) and read the new voices' drafts next to the old ones (`scripts/swan_view.py`). Ship by merging to `main`.

## Done when
6 new personas are in `content.PERSONAS`, reviewed by a person, with tests passing. The bot registers them as room allows, and the team knows which voice replaces whom.
