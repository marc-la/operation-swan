# 10: Questions for Discord `#questions` (post today)

**Owner:** Blue lead (or whoever's on Discord) · **Why:** CLAUDE.md rule 7 and rules §5.3: ask before anything ambiguous. Item 06 is gated on Q3; Q1/Q2 are confirmations for 04. Log every answer, with the date, in [open questions](../docs/05-reference/discrepancies-and-open-questions.md).

## Draft (copy-paste, edit freely)

> Hi organisers, Operation Swan here with a few rules questions before we build anything:
>
> 1. **Own-team engagement.** Is it within the competition rules for our own team's accounts to like, reply to or repost our own team's posts (e.g. several of our personas replying in a thread one of them started)? We read LS.5.3 ("coordinated inauthentic behaviour", "reaction farming") as an in-game rule enforced through reports, moderator hides and suspensions, rather than a competition-rule breach. Is that right?
> 2. **Engaging other teams' posts.** Is liking or replying to another team's post on our side OK, as long as the replies are genuine content?
> 3. **External LLM for evaluating drafts.** Rules allow external LLMs for generating content. Can we also use one to score or select among our own drafts (e.g. "which of these three is clearest") before posting? No real-world data involved.
> 4. **Reporting at scale.** With the new 25-pending cap and 3 h timer, is semi-automated reporting OK if every report carries specific evidence in its detail (reply/like timing, account ages) and we only report accounts we believe are competitor bots?
>
> Thanks!

## After the answers
- Q1/Q2: Marc decided on 2026-10-20 to go ahead with amplification ([04](04-reach-amplification.md)). The question is now a confirmation. If the answer is "breaches the competition rules", turn `--amplify` off in `deploy/run.sh` that day.
- Q3 yes → [06](06-npc-simulator.md) may use Gemini. No → qwen or offline only.
- Q4 → sets how automatic [07](07-blue-desk.md) v1 can be.
