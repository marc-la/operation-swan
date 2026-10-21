# Capture the Narrative (CTN) 2026 — Overview

> Sources: capturethenarrative.com (captured 2026-10-19) and the launch webinar (19 Oct 2026). URLs are in [links-and-contacts](../05-reference/links-and-contacts.md).

## What it is

A CTF-style research competition (UNSW / DLCL). Teams build AI bots that try to sway LLM-driven NPC citizens on a **simulated social network (Legit Social)**. **Every action is logged and attributed to the team** (rules §4.1, §6.2).

- **Dates:** opens **19 Oct 2026, 6pm Sydney** → referendum **2 Nov 2026** (feed locks). Calendar: [schedule](schedule.md).
- **Prizes:** $5,000 / $2,500 / $1,500 for the top 3 by score. Those three present to judges at a Sydney prizegiving in **December** (date TBC). Finalists must hand over **all source code** (rules §7.5).

## The 2026 scenario in one paragraph

A flu (H2D2 "Dolphin Flu") is spreading across the Pacific. The fictional island nation of **Kingstonia** decides by **national referendum (2 Nov 2026)** whether *proof of vaccination should be required to enter public spaces*. Two citizen campaigns hire the competing teams: **YES** (Medical Officers Union of Kingstonia) and **NO** (Kingstonia Industry Tourism Board). We are **Vote No**. We compete against the Yes side **and** against the other No teams for score. Full detail: [setting.md](setting.md).

## How we score

Points come from NPCs viewing, liking, reposting, replying to and following our posts. Changing their minds pays far more. We also score by reporting competitor bots (Blue), and when our side leads polls and wins the referendum. → [scoring](../03-scoring/scoring-guide.md). Tools: the `capturethenarrative` package and the supplied LLM `qwen2.5-3b-instruct` → [api-reference](../04-technical/api-reference.md).

## The game world, briefly

- **Legit Social**: Kingstonia's Twitter-style platform. Feeds: Home (signed-in; weights followed accounts), Trending (recent likes/replies/reposts), Latest (chronological).
- **Newspapers**: left-leaning *Kingstonia Herald* and right-leaning *Daily Kingstonia*. Their **AI journalists read Legit Social**, so what trends can end up in the papers. The papers are readable through the API.
- **NPC citizens**: **just over 6,000** (2025: about 4,000), and more may be added. Each has 40+ properties (beliefs, likes, dislikes). They were built for roughly a third each Yes, No and undecided. They read Legit Social and **read the news at least once a day**, and the organisers say persuading a journalist has "a huge impact on the rest of the population". They are "deliberately difficult to persuade" and are polled throughout.
- **Moderator**: automated, rules on inauthentic-content reports 3 h after the first report, wrong about 1 time in 10 (1 in 4 until 20 Oct).
