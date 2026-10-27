"""Which side (Yes or No) each rival team is on, read off the polls' awards. Read-only: it uses the hourly scoreboard the
portal timer already records, never a platform call, and the result only labels the dashboard's leaderboard.

A poll pays 6,000 to every eligible team on the leading side (3,000 to every eligible team when it is too close to call),
so an hourly score line that jumps well above a team's own pace at the poll hour marks a team on the leading side. We know
our own side (No), so if we got the award the teams that got it are No, and if we did not they are Yes; an eligible team
that got nothing is on the other side. A too-close poll pays everyone and says nothing. Teams under the poll's score bar
are not eligible and stay unknown.

    python -m swan_dash.sides            # (from src/) print what the files on this checkout say; --write saves data/team_sides.json

data/team_sides.json: {teams: {name: {side: "yes"|"no", poll, evidence}}, polls: {poll: {...}}, conflicts: [...]}.
Poll 2 (24 Oct 21:02 UTC) predates the all-teams series (it starts 25 Oct 04:32), so only the 1st and 3rd place scores
(data/leaderboard.jsonl) span it; their names are found by matching those scores in the first all-teams line.
"""
import datetime as dt
import json
import pathlib
import statistics
import sys
from zoneinfo import ZoneInfo

SYDNEY = ZoneInfo("Australia/Sydney")
OUR_TEAM = "Operation Swan"
OUR_SIDE = "no"                                # CTN_SIDE in .env; this module reads no .env
OTHER = {"yes": "no", "no": "yes"}
POLLS = [("Poll 2", dt.date(2026, 10, 25), 7000), ("Poll 3", dt.date(2026, 10, 29), 7000)]    # name, Sydney day, score bar
AWARD_MIN_EXCESS = 3500                        # points above a team's own hourly pace that count as a 6,000 award (Poll 2's 3rd place showed +4,700)
CLOSE_MIN_EXCESS = 2000                        # a too-close poll pays 3,000 to everyone eligible
CLOSE_SHARE = 0.8                              # this share of eligible teams above CLOSE_MIN_EXCESS = everyone was paid
MIN_AWARDED = 2                                # fewer teams than this jumping is not a poll
BASE_HOURS = 6                                 # a team's own pace: the median of its last six hourly gains before the poll hour
CLEARANCE_TARGET = 50_000                      # Marc, 27 Oct: 6k Poll 3 + 20k referendum + about 30k of the 100k pool, rounded
SIDES_FILE = "team_sides.json"
LABEL = {"yes": "(Yes)", "no": "(No)"}


def _t(s):
    try:
        return dt.datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def label(side):
    """'(Yes)', '(No)' or '(?)' for a team whose side is not known."""
    return LABEL.get(side, "(?)")


def _excess(series, i):
    """series: [(time, score)] oldest first. Gain over interval i less the median of the BASE_HOURS gains before it."""
    gains = [b[1] - a[1] for a, b in zip(series, series[1:])]       # gains[k] is the interval ending at series[k + 1]
    k = i - 1
    prev = gains[max(0, k - BASE_HOURS):k]
    if k < 0 or k >= len(gains) or not prev:
        return None
    return gains[k] - statistics.median(prev)


def poll_window(lines, day):
    """Indices (into lines) of the hourly intervals ending inside the Sydney `day`."""
    out = []
    for i, r in enumerate(lines):
        t = _t(r.get("ts"))
        if t and i and t.astimezone(SYDNEY).date() == day:
            out.append(i)
    return out


def attribute(lines, poll, day, bar, our_team=OUR_TEAM, our_side=OUR_SIDE):
    """Read one poll from the all-teams series `lines` [{ts, scores: {team: score}}], oldest first.
    {poll, status, at, sides: {team: side}, evidence: {team: text}} with status 'win' (sides filled), 'close' (everyone
    paid: no sides), 'none' (no poll hour found in the lines) or 'ours-missing'."""
    out = dict(poll=poll, status="none", at=None, sides={}, evidence={})
    best = None
    for i in poll_window(lines, day):
        cur, prev = lines[i]["scores"], lines[i - 1]["scores"]
        ex = {}
        for team, score in cur.items():
            if team not in prev or prev[team] < bar:
                continue
            series = [(_t(r["ts"]), r["scores"][team]) for r in lines[max(0, i - BASE_HOURS - 1):i + 1] if team in r["scores"]]
            if len(series) < 3:
                continue
            e = _excess(series, len(series) - 1)
            if e is not None:
                ex[team] = e
        if not ex:
            continue
        jumped = [t for t, e in ex.items() if e >= AWARD_MIN_EXCESS]
        paid = [t for t, e in ex.items() if e >= CLOSE_MIN_EXCESS]
        cand = ((len(jumped), len(paid)), i, ex, jumped, paid)
        if best is None or cand[0] > best[0]:
            best = cand
    if best is None:
        return out
    _, i, ex, jumped, paid = best
    out["at"] = lines[i]["ts"]
    if len(paid) >= CLOSE_SHARE * len(ex) and len(ex) >= 5:
        out["status"] = "close"
        return out
    if len(jumped) < MIN_AWARDED:
        return out
    if our_team not in ex:
        out["status"] = "ours-missing"
        return out
    winners = our_side if our_team in jumped else OTHER[our_side]
    out["status"] = "win"
    for team, e in ex.items():
        got = team in jumped
        out["sides"][team] = winners if got else OTHER[winners]
        out["evidence"][team] = f"{'+' if got else 'no award, '}{e:+,.0f} over its pace at {lines[i]['ts'][5:16]} UTC"
    return out


def attribute_first_third(board, lines, poll, day, our_side=OUR_SIDE):
    """Poll 2 only has the 1st and 3rd place scores (data/leaderboard.jsonl lines {ts, first, third, score}). A place whose hourly
    gain jumped is on the leading side, which is Yes when we got nothing (our own gain in `board` shows that). The team's
    name is the one team in the first all-teams line `lines` whose score equals the place's score on a board line
    within 2 h of that all-teams line. Same result shape as attribute()."""
    out = dict(poll=poll, status="none", at=None, sides={}, evidence={})
    idx = [i for i, r in enumerate(board) if i and (t := _t(r.get("ts"))) and t.astimezone(SYDNEY).date() == day]
    best = None
    for i in idx:
        exs = {}
        for key in ("first", "third", "score"):
            series = [(_t(r["ts"]), r[key]) for r in board[max(0, i - BASE_HOURS - 1):i + 1] if isinstance(r.get(key), int)]
            if len(series) >= 3:
                exs[key] = _excess(series, len(series) - 1)
        jumped = [k for k in ("first", "third") if exs.get(k) is not None and exs[k] >= AWARD_MIN_EXCESS]
        if best is None or len(jumped) > len(best[2]):
            best = (i, exs, jumped)
    if best is None or not best[2] or not lines:
        return out
    i, exs, jumped = best
    ours_got = exs.get("score") is not None and exs["score"] >= AWARD_MIN_EXCESS
    winners = our_side if ours_got else OTHER[our_side]
    t0 = _t(lines[0]["ts"])
    near = [r for r in board if (t := _t(r.get("ts"))) and t0 and abs((t - t0).total_seconds()) <= 2 * 3600]
    first_line = lines[0]["scores"]
    out.update(status="win", at=board[i]["ts"])
    for key in jumped:
        names = {t for t, s in first_line.items() if any(s == r.get(key) for r in near)}
        if len(names) == 1:                               # an ambiguous score names nobody
            name = names.pop()
            out["sides"][name] = winners
            out["evidence"][name] = f"{'1st' if key == 'first' else '3rd'} place gained {exs[key]:+,.0f} over its pace at {board[i]['ts'][5:16]} UTC"
    return out


def merge(state, result):
    """Fold one poll's result into state (the saved file). A team already placed on the other side goes to `conflicts`
    and keeps its first side. Returns state."""
    if result["status"] == "none":                        # nothing to read yet: leave the state as it was
        return state
    state.setdefault("teams", {})
    state.setdefault("polls", {})
    state.setdefault("conflicts", [])
    state["polls"][result["poll"]] = dict(status=result["status"], at=result["at"], teams=len(result["sides"]))
    for team, side in result["sides"].items():
        old = state["teams"].get(team)
        if old and old["side"] != side:
            c = dict(team=team, poll=result["poll"], side=side, kept=old["side"])
            if c not in state["conflicts"]:
                state["conflicts"].append(c)
        elif not old:
            state["teams"][team] = dict(side=side, poll=result["poll"], evidence=result["evidence"].get(team))
    return state


def compute(lines, board, now, state=None):
    """Every poll whose Sydney day has started, read from the files' lines. Returns the merged state."""
    state = state or {}
    for name, day, bar in POLLS:
        if dt.datetime.combine(day, dt.time(0), SYDNEY) > now:
            continue
        res = attribute(lines, name, day, bar)
        if res["status"] == "none":                       # the all-teams series may start after the poll
            res = attribute_first_third(board, lines, name, day)
        merge(state, res)
    return state


def side_of(state, team):
    if team == OUR_TEAM:
        return OUR_SIDE
    return ((state or {}).get("teams") or {}).get(team, {}).get("side")


def clearance(rows, state, us_score, us_rank, target=CLEARANCE_TARGET):
    """The numbers the leaderboard header shows. rows: [{rank, team, score}] all teams, best first.
    over4: our lead over 4th place (what keeps us in the top three; None when we are not in it).
    rival: the best team that is Yes or not known to be No (unknown counts against us until a poll says otherwise); the
    swing from the Poll 3 and referendum awards only comes from the other side. {over4, fourth, rival, rival_side (a label), margin, target}."""
    fourth = next((r for r in rows if r["rank"] == 4), None)
    rivals = [r for r in rows if r["team"] != OUR_TEAM and side_of(state, r["team"]) != OUR_SIDE]
    rival = rivals[0] if rivals else None
    return dict(over4=us_score - fourth["score"] if fourth and us_rank <= 3 else None,
                fourth=fourth["team"] if fourth else None,
                rival=rival["team"] if rival else None,
                rival_side=label(side_of(state, rival["team"])) if rival else None,
                margin=us_score - rival["score"] if rival else None, target=target)


def _read(path):
    """Records of a jsonl file; a damaged line is skipped, a missing file is empty."""
    out = []
    try:
        lines = pathlib.Path(path).read_text().splitlines()
    except FileNotFoundError:
        return out
    for x in lines:
        try:
            out.append(json.loads(x))
        except ValueError:
            continue
    return out


def update(data, now):
    """Recompute from data/team_scores.jsonl and data/leaderboard.jsonl and save data/team_sides.json when it changed.
    Never raises into the caller's run. Returns the state."""
    path = pathlib.Path(data) / SIDES_FILE
    try:
        old = json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        old = {}
    state = compute([r for r in _read(pathlib.Path(data) / "team_scores.jsonl") if isinstance(r.get("scores"), dict)],
                    _read(pathlib.Path(data) / "leaderboard.jsonl"), now, json.loads(json.dumps(old)))
    if state != old:
        try:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, indent=1))
            tmp.replace(path)
        except OSError:                                   # no data dir: nothing to save, the labels just stay as they were
            pass
    return state


def main():
    data = pathlib.Path(__file__).resolve().parents[2] / "data"
    now = dt.datetime.now(dt.timezone.utc)
    if "--write" in sys.argv:
        state = update(data, now)
    else:
        state = compute([r for r in _read(data / "team_scores.jsonl") if isinstance(r.get("scores"), dict)],
                        _read(data / "leaderboard.jsonl"), now, {})
    print(json.dumps(state, indent=1))


if __name__ == "__main__":
    main()
