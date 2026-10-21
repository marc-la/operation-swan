#!/usr/bin/env bash
# Record the portal score for the dashboard (todo/09) until we may read the portal automatically.
#   ssh swan-ec2 'ctn/scripts/score.sh 3140 14 145 kim'     # score, rank, teams on the board, who typed it
# Appends to data/score.json; the dashboard shows the latest entry and the change since the day rolled over.
set -euo pipefail
cd "$(dirname "$0")/.."
[ $# -ge 2 ] || { echo "usage: scripts/score.sh <score> <rank> [teams] [who]"; exit 1; }
mkdir -p data
.venv/bin/python - "$@" <<'EOF'
import datetime as dt, json, os, pathlib, sys
score, rank = int(sys.argv[1].replace(",", "")), int(sys.argv[2])
teams = int(sys.argv[3]) if len(sys.argv) > 3 else None
who = sys.argv[4] if len(sys.argv) > 4 else os.environ.get("CTN_OPERATOR", "marc")
path = pathlib.Path("data/score.json")
try:
    entries = json.loads(path.read_text())
except (FileNotFoundError, json.JSONDecodeError):
    entries = []
entries.append(dict(ts=dt.datetime.now(dt.timezone.utc).isoformat(), score=score, rank=rank, teams=teams, by=who))
tmp = path.with_suffix(".tmp")
tmp.write_text(json.dumps(entries, indent=1))
os.replace(tmp, path)
print(f"recorded {score:,} (rank {rank}) by {who}")
EOF
