"""Operation Swan Blue track (todo/07, docs/06-strategy/blue-reporting.md): find competitor ring bots, report them.

A separate process from swan_bot (deploy/swan-blue.service). It reports from one account the bot no longer uses
(swan_bot.config.blue_reporter), and only touches the report routes, which have their own team budget. It never
writes secrets/swan_accounts.json.

    python -m swan_blue                        # (from src/) dry run: scan and rank, file nothing
    python -m swan_blue --live                 # what swan-blue.service runs
    python -m swan_blue approve 133074,a4955   # approve candidates (scripts/blue.sh wraps this for ssh)
    python -m swan_blue approve all
"""
