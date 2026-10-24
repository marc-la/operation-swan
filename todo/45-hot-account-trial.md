# 45 — Hot account: all writing through one voice at a time (trial)

Written 2026-10-24 (Marc + Claude). Read `CLAUDE.md` first. Code: `config.HOT_VOICES` / `hot_mode_apply`, `Accounts.voices` / `hot`, `bot.hot_note`, send-time `voice_gone_at_send`; runbook "2026-10-24: hot account". Tests `tests/test_hot_voice.py`.

## Why
- 24 Oct: 3,826 writes and 27 bans in 24 h (about 142 writes a ban; 171 [143, 190] by Kaplan-Meier); spare registrations run out about 29–30 Oct, before the x4 days. The write rate is the driver; the hide rate is flat (about 1.4–2%).
- ctn-1c's read of our own hides (113 matched): rivals report in sweeps, a voice loses ONE post per sweep (86 of 87), the chance of a hit grows about pace^0.6, one or two chasing teams, first hide to ban median 7.4 h. A voice at the team rate (about 170 writes an hour) would then die in roughly 6–11 h, 1,000–2,000 writes, against 171 now. **Break-even is surviving about an hour at 170 an hour.**
- Extrapolation: the highest observed pace is about 15 writes an hour; this is 10x beyond it. That is the trial's question.

## Risks to watch (not blockers)
- A rival's account report needs only 1 hidden post + 100 actions; a hot voice passes 100 actions in under an hour, and a report "this account posted 180 times in an hour" may well be upheld. Account-route bans (about 10 of 36 so far) are the likeliest early death.
- One persona for every conversation: frames outside its home set, repeated wording, and possibly weaker persuasion per reply. Read points per hour against the last 24 h (about 1,000 an hour, 16 voices) as well as writes per ban.
- LS.5.3 ("repetitive low-quality posting", automated accounts) is the in-world basis for restricting it; the team rate cap is unchanged. Marc's call whether to ask `#questions` first (draft in the chat of 24 Oct).

## Trial (proposal; nothing is switched on)
1. Roster: three active voices with ZERO hidden posts (no account-report standing yet), preferably the ~92 h ones: `ana_d94` (kiri), `tui4` (sione), `vika68` (esther); `jess_h99` (paulo) is a fourth. No registering or converting is needed. Check `data/swan_watch.json` for hides first.
2. Park the others by leaving them out (they stay active and untouched; any with a hidden post can still be reported idle). Do NOT whittle: that spends accounts at 25 a day for nothing.
3. `.env`: `SWAN_HOT_VOICES=ana_d94,tui4,vika68`; restart `swan-bot` (the pool then logs shadow rows only). Start in a Sydney-quiet block (report timing 21–24 about 3 per 1,000 writes against 17–20 in 06–15).
4. Read out per voice: writes at suspension, hits per sweep, first hide to ban, route (3 posts hidden / reported as a bot), and score per hour.
5. Stop and go back (unset, restart) if: two hot voices are gone in under 2 h each (under ~340 writes, no better than now), or points per hour fall more than a third below the last 24 h with no better writes per ban. Keep it if writes per ban beat 171 clearly; then decide how far to cut the others.
