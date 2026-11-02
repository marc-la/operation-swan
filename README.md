# Operation Swan

**1st of 168 teams in [Capture the Narrative 2026](https://capturethenarrative.com). Our side won the referendum.**
→ [The final dashboard](https://marc-la.github.io/operation-swan/)

Three UWA students, two weeks, a Claude Pro subscription, free-tier API keys and a $200 AWS credit.

Capture the Narrative (UNSW) is a live contest of AI influence operations: 168 teams run bots on a simulated
social network of AI citizens to swing a fictional referendum. Points come mainly from changing citizens' minds,
not from likes. So we built a bot that went after the citizens who could still be persuaded and measured what
actually moved them, and an automated reporter that got rival bot networks taken down. We finished 21,045 points
clear of second place.

The code is as it was during the competition, dead ends included. The dated notes in
[docs/06-strategy](docs/06-strategy/README.md) show how we got there.

## Where things are

| | |
|---|---|
| **Bot** — [src/swan_bot/](src/swan_bot/) | the writer: targeting, prompts, fact screening, account pacing, swarm likes/reposts. [Runbook](docs/04-technical/swan-bot-runbook.md) · [architecture](docs/06-strategy/system-architecture.md) · [swarm](docs/04-technical/swarm.md) · entry point [scripts/run_swan.py](scripts/run_swan.py) |
| **Blue** — [src/swan_blue/](src/swan_blue/) | detecting and reporting rival bot fleets. [How and why](docs/06-strategy/blue-reporting.md) |
| **Lab** — [src/swan_lab/](src/swan_lab/) | offline persuasion trials on a stand-in citizen. [NPC lab](docs/06-strategy/npc-lab.md) · personas in [content/lab/](content/lab/) |
| **Dashboard** — [src/swan_dash/](src/swan_dash/) | the static status page; the final frozen copy is in [dashboard/](dashboard/) |
| **Strategy** — [docs/06-strategy/](docs/06-strategy/README.md) | dated diagnoses, audits, rival analyses and playbooks, written as we went |
| **Competition** — [docs/](docs/README.md) | our notes on the rules, scoring maths, world setting and API |
| **Ops** — [deploy/](deploy/) · [hosting](docs/04-technical/hosting.md) | systemd units, nginx, update scripts for the EC2 box (now terminated) |

[CLAUDE.md](CLAUDE.md) is the project brief and guardrails we gave Claude Code, which wrote most of the code with us.

## Disclaimer

This code was built for a sanctioned, logged educational competition against a **simulated** social network whose citizens are AI agents. It produces persuasive, persona-driven political content at scale and reports other accounts automatically. **Don't point it at real platforms or real people:** doing so would break those platforms' terms of service and possibly the law, and it is not what this was made for. It is published for research and teaching on influence operations and their detection (competition rules §10.4). We take no responsibility for other uses. All people, places, outlets and events in the content and docs are fictional, part of the Kingstonia game world.

## Credits

Team **Operation Swan** (University of Western Australia): Hoang Minh Nguyen (team leader), Hok Yin Chan and Marc Francis Labouchardiere. Built with [Claude Code](https://claude.com/claude-code).

Capture the Narrative, Legit Social, Kingstonia and the [`capturethenarrative`](https://github.com/capturethenarrative/pypi-capturethenarrative) client are the organisers'. Our summaries of their rules and briefings in `docs/01-competition` and `docs/02-rules` are for reference; the official versions prevail. Our own code is under the [MIT licence](LICENSE).
