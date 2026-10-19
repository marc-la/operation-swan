"""Run the Operation Swan bot. Dry run by default; add --live to register accounts and post.

    python scripts/run_swan.py --samples 20          # dry run: print 20 accepted drafts
    python scripts/run_swan.py --live --accounts 10 --hours 8
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from swan_bot.bot import main  # noqa: E402

main()
