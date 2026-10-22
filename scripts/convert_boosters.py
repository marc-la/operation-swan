"""Turn like-only boosters into writing voices, each on the persona card of a suspended voice (22 Oct: 13 of 17 voices
suspended, the persona cards all used, so the bot could not register replacements and throughput fell to ~1.1/min).
DRY RUN unless --apply. Stop the bot first: it rewrites secrets/swan_accounts.json and would undo the change.

    python scripts/convert_boosters.py                    # the plan: which booster takes which card
    sudo systemctl stop swan-bot
    python scripts/convert_boosters.py --apply --by marc  # rewrite the records, log one 'convert' per account
    sudo systemctl start swan-bot

A converted account keeps its username, display name and owner. It drafts under its own name with the card's role,
place, frames and argument, but not the old voice's people, lines or events, in another card's style and typing hand
(bot.persona_of), and sleeps its own hours (stealth.key_of); todo/31's caps hold for it as for any voice. The record
notes when, by whom, whose card and whose style it took. Lower --boosters in deploy/run.sh by as many, or the drip
registration tops the boosters back up.
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot import config, content  # noqa: E402

# (booster, persona card, style card) in the order they are converted, booster names matched to the card. Cards whose
# voice was suspended by an account report on one hidden post come first (wally, dan, priya); mere, paulo and ben, whose
# posts were hidden 3-5 times, are left out as cards and lend only a style. The style card (voice, register, typing
# hand) is never the card's own: bot.persona_of.
PLAN = [("owen_bakes", "wally", "mere"), ("malakai_r94", "dan", "ben"), ("ivy76", "priya", "paulo"),
        ("jess_f77", "grace", "priya"), ("ellaleota", "isla", "lani"), ("marcotaufa", "josh", "tomasi"),
        ("vika_i92", "ruth", "grace"), ("rua90", "tomasi", "josh"), ("lucy.pulu", "lani", "isla"),
        ("rwalker84", "sione", "dan")]


def plan(records, n, pairs=PLAN):
    """[(rec, persona key, style key)] for the first n that may be converted, and [(username, why)] for the rest."""
    reporter = config.blue_reporter(records)
    by_name = {r["username"]: r for r in records}
    taken = {r["persona"] for r in records if r.get("role", "voice") != "booster"
             and r.get("status", "active") == "active"}
    ok, skipped = [], []
    for username, key, style in pairs:
        rec = by_name.get(username)
        why = ("no such account" if rec is None else
               "not a booster" if rec.get("role") != "booster" else
               "not active" if rec.get("status", "active") != "active" else
               "Blue's reporter" if rec is reporter else
               "no such card" if key not in content.PERSONA_BY_KEY or style not in content.PERSONA_BY_KEY else
               "style is the card's own" if style == key else
               "card held by an active voice" if key in taken else
               "style of an active voice" if style in taken else
               "enough" if len(ok) >= n else None)
        if why:
            skipped.append((username, why))
        else:
            ok.append((rec, key, style))
            taken.add(key)
    return ok, skipped


def convert(records, todo, by, now=None):
    """Make each (rec, key, style) a voice on that card in that style, in place. Returns the log lines."""
    now = now or dt.datetime.now(dt.timezone.utc).isoformat()
    old = {r["persona"]: r["username"] for r in records if r.get("role", "voice") != "booster" and r.get("persona")}
    lines = []
    for rec, key, style in todo:
        rec.update(role="voice", persona=key,
                   converted=dict(at=now, by=by, from_role="booster", card_of=old.get(key), style_of=style))
        lines.append({"ts": now, "act": "convert", "username": rec["username"], "account_id": rec.get("account_id"),
                      "persona": key, "card_of": old.get(key), "style_of": style, "owner": rec.get("owner"), "by": by})
    return lines


def bot_running():
    return subprocess.run(["pgrep", "-f", "scripts/run_swan.py"], capture_output=True).returncode == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", type=int, default=len(PLAN), help=f"boosters to convert (default {len(PLAN)})")
    ap.add_argument("--apply", action="store_true", help="rewrite the account records (default: print the plan)")
    ap.add_argument("--by", help="team member who decided this (required with --apply)")
    args = ap.parse_args()
    records = json.loads(config.ACCOUNTS_FILE.read_text())
    todo, skipped = plan(records, args.n)
    for rec, key, style in todo:
        card = content.PERSONA_BY_KEY[key]
        print(f"convert @{rec['username']} ({rec.get('display_name')}, id {rec.get('account_id')}) -> card {key} "
              f"({card['role']}, {card['place']}), style of {style}")
    for username, why in skipped:
        print(f"skip    @{username}: {why}")
    if not args.apply:
        print(f"\ndry run: {len(todo)} to convert. Stop swan-bot, then --apply --by <name>.")
        return
    if not args.by:
        sys.exit("--apply needs --by <team member>")
    if bot_running():
        sys.exit("swan-bot is running: it would overwrite the records. sudo systemctl stop swan-bot first.")
    lines = convert(records, todo, args.by)
    tmp = config.ACCOUNTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(records, indent=1))
    os.chmod(tmp, 0o600)
    os.replace(tmp, config.ACCOUNTS_FILE)
    config.LOGS.mkdir(exist_ok=True)
    with open(config.ACTIONS_LOG, "a") as f:
        f.writelines(json.dumps(x) + "\n" for x in lines)
    print(f"\nconverted {len(lines)}. Start swan-bot.")


if __name__ == "__main__":
    main()
