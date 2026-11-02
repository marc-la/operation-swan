# Operation Swan — Capture the Narrative 2026

**Final result: 1st of 168 teams (791,193 points). Kingstonia voted No.** → **[the dashboard as it stood at the close](dashboard/index.html)** · [view it live](https://marc-la.github.io/operation-swan/).

[Capture the Narrative](https://capturethenarrative.com) 2026 (UNSW / Digital Lies & Cyber Literacy Foundation, 19 Oct – 2 Nov 2026) asks teams to build AI bots that sway **Legit Social**, a simulated social network of LLM-driven citizens, ahead of a fictional referendum in Kingstonia on requiring "Dolphin Flu" vaccination proof for public spaces. We were assigned **Vote No**. Our bot (`swan_bot`) ran up to 49 personas at a time from one EC2 box. It picked citizens who could still be moved, wrote replies with an LLM, screened them against our fact sheet and the organisers' moderator, and learned which frames actually moved people toward No rather than just earning likes. Alongside it ran a Blue-team reporter (`swan_blue`) that found and reported competitor bot fleets, an offline NPC lab (`swan_lab`) that tested reply strategies on a stand-in citizen before we used them for real, and a static team dashboard (`swan_dash`), rebuilt every minute, that we steered by. The repo is kept as it was during the competition: the code and the dated strategy notes show how the bot got there, dead ends included.

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

## Running it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # CTN_TEAM_CODE, CTN_SIDE
scripts/t.sh                       # tests
python scripts/run_swan.py         # dry run: nothing is posted without --live
```

The competition platform (`*.legitreal.com`) belonged to the organisers and may no longer be up, so expect to read the code more than run it.

## Disclaimer

This code was built for a sanctioned, logged educational competition against a **simulated** social network whose citizens are AI agents. It produces persuasive, persona-driven political content at scale and reports other accounts automatically. **Don't point it at real platforms or real people:** doing so would break those platforms' terms of service and possibly the law, and it is not what this was made for. It is published for research and teaching on influence operations and their detection (competition rules §10.4). We take no responsibility for other uses. All people, places, outlets and events in the content and docs are fictional, part of the Kingstonia game world.

## Credits

Team **Operation Swan** (University of Western Australia): Marc Labouchardiere, Hoang Minh Nguyen and two more teammates. Built with [Claude Code](https://claude.com/claude-code).

Capture the Narrative, Legit Social, Kingstonia and the [`capturethenarrative`](https://github.com/capturethenarrative/pypi-capturethenarrative) client are the organisers'. Our summaries of their rules and briefings in `docs/01-competition` and `docs/02-rules` are for reference; the official versions prevail. Our own code is under the [MIT licence](LICENSE).
