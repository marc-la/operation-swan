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

## Drafted 2026-10-21: five candidates, not yet live
Five voices are drafted, chosen for the shapes that trend (conversion story, named loss, long memory) and for the biggest gaps. They are in `characters.CANDIDATES` (the last five) with their typing hands in `humanize.CANDIDATE_HANDS`, and the tests pass. Because none is in `content.PERSONAS`, **the bot registers none of them yet**. Why each one should trend, plus gold texts to read: [new-voices-2026-10-21](../docs/06-strategy/new-voices-2026-10-21.md).

| Key | Who | Replaces / fills | Register | Identities to add to `targeting.IDENTITIES` |
|---|---|---|---|---|
| `esther` | Bakery owner by the Kingstonia City markets (idea 1's small-business slot, not tourism) | **Lani's slot**: `shop` has no live messenger | warm | shop, parent |
| `paulo` | Warehouse dad; daughter turns 12 in March; was leaning Yes after losing his father in COVID | ideas 5 + 10: the conversion voice; the first father | warm | parent |
| `ngaire` | Volunteer netball coach, Crown Harbour; freight clerk by day | idea 6: sport, parks, volunteers | fed_up | **sport** (new), parent |
| `wally` | Retired New Haven harbour-master, 74 | idea 8: older men; Yes wins older readers | warm | **older** (new), parent |
| `kai` | Marine-monitoring software developer, Kingstonia City | idea 4: tech, ID card and data for the "Yes, but" crowd | plain | **tech** (new) |

Not drafted: the resort housekeeper (idea 2), because "resort" is in `content._OFF_LIMITS`, so most of her profile would be cut from every prompt. Tourism is covered by the earlier candidate `rafa`. The earlier candidates `kiri`, `rafa` and `leo` remain as reserves. Note that kiri has a line about having "had every childhood jab" and a COVID line mentioning resorts, and the prompt filter drops both.

**For a person to decide before promoting:**
Decided 2026-10-21 (Marc):
- Paulo's late father stays as written.
- Claims now say only what the question or setting.md says. "Nobody has said who checks" became "the question doesn't say who checks" (Ngaire, Kai, and Dan's existing line). "A Yes has no take-backs" / "can't be undone" became "after a Yes the government has to bring it in", with no end date (isla's line, the F2 heat in `craft.py`, the `status_quo` lever in `content.py`, and the playbook's dead-word note).

Still open:
1. Kai and his partner Vika share first names with boosters (`amplify.FIRST`). Existing characters already share some names (Kalo, Noa, Salote), so this is minor.
2. Wally dropped F9 (parliament) for F12. Wally's "green bananas" mortality joke: keep it?
3. Invented local colour: Saltworks Park (Ngaire) and "keke" doughnuts (Esther).

**To promote one:** move its dict from `CANDIDATES` into `content.PERSONAS` (the `key/name/handle/role/place/voice/details/frames` fields) and `CHARACTERS` (the profile fields), add its register to `voices.VOICE_OF` and its hand from `CANDIDATE_HANDS` to `HANDS`, add its identities to `targeting.IDENTITIES` (new `sport`, `older` and `tech` patterns too), update the counts in `test_characters.py` and `test_prompts.py`, then dry-run (`scripts/run_swan.py --samples 12`). Registration then starts on deploy.

## Promoted 2026-10-21 (Marc approved the open points above)
All five are in `content.PERSONAS` (registration order: esther, paulo, wally, ngaire, kai), with profiles in `CHARACTERS`, registers in `voices.VOICE_OF` and hands in `HANDS`. `targeting.IDENTITIES` gained `sport` (ngaire), `older` (wally, mere) and `tech` (kai); esther joins `shop`, and the parents join `parent`. Kai's `voice` no longer says "asks who switches it off": that is the `no_end` fact, and the voice field isn't filtered when a fact is paused.

Caps: `--accounts 16`, `config.MAX_ACCOUNTS` 21, `config.MAX_ACTIVE` 49 (one of the platform's 50 is a team member's own account: the portal counts 47 registered, our records 46). Boosters stay at 34, since they can't be removed without deleting accounts. So esther, paulo, wally and ngaire register now, one every 20–40 min, and **kai waits** until a voice is suspended. To bring kai in sooner, someone frees a slot: delete one booster (irreversible) or the manual account.

## Done when
6 new personas are in `content.PERSONAS`, reviewed by a person, with tests passing. The bot registers them as room allows, and the team knows which voice replaces whom.
