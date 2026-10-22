# 30: Voices for the long game. Replace the lost ones, keep a reserve for ×2 and ×4

**Owner:** orchestrator (ctn-9c) · **When:** after todo/27 is live and hides fall · **Blocked on Marc's explicit go** (CLAUDE.md rule 8: registering accounts)

## Why (2026-10-22 ~05:00 UTC)
- Portal: **55 registered, 7 banned**, max 200 total / 50 active. Hidden posts on our voices per hour: 2, 5, 6 today (alerts.log). Only ~7 voices still write; six sit at 2 hidden (`HIDDEN_STOP`).
- Persuasion points are worth ×2 from 26 Oct and ×4 from 1 Nov (derived; verify). A voice burned now costs more later. **Budget: 145 accounts left** for 11 days.
- Re-running the old personas from the deleted todo/17 as they were would burn them again: the fingerprint (todo/27) is in the text, not the name.

## Plan
1. **Gate:** todo/27 is live, and our hides are < 1/h for 6 h (alerts.log). Until then new voices would be reported like the old ones.
2. **Wave 1 (now + gate): 6 new voices.** New personas with distinct voice, length, rhythm and topics; no shared closing or skeleton (todo/27's phrase budgets apply per voice too). Build them from the persona format the bot uses (`content.py` personas, owned by the todo/25 session: ask it for the cards). Max 6 citizen writes/h each (todo/27).
3. **Reserve: keep ≥ 40 unregistered accounts** for 26 Oct (×2) and ≥ 30 for 1 Nov (×4). Register the ×2 wave on 25 Oct, so the voices are a day old and have some ordinary activity before the multiplier.
4. **Retire before suspension:** a voice at 2 hidden stops (today). Ask the organisers whether **deleting our own older posts** from a voice at 2 hidden is acceptable (rules §9 / "spirit": it could read as dodging moderation, so ask before doing it). Draft for `#questions`:
   > Operation Swan here. If one of our accounts has 2 moderator-hidden posts, may we delete that account's own older posts (DELETE /posts/{id}) to lower its exposure to further reports, or would you treat that as evading moderation? We'd rather ask than guess.
5. **Measure per wave:** hides per voice per 100 writes, and changes of mind per voice, so the next wave copies what lasted.

## Ownership
Registration and persona cards only after Marc's go. `content.py` stays with the todo/25 session.
