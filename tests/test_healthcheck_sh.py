"""deploy/healthcheck.sh (25 Oct uptime check): "writing" means a live text write by swan-bot, not a booster's like or the
swarm's repost; a problem is alerted when it starts, hourly while it lasts and once when it clears. Offline: the script runs
in a tmp tree with systemctl and alert.sh as shims."""
import datetime as dt
import json
import os
import shutil
import subprocess

import pytest

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def iso(min_ago):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=min_ago)).isoformat()


class Box:
    def __init__(self, tmp):
        self.root, self.calls = tmp / "ctn", tmp / "calls.log"
        (self.root / "deploy").mkdir(parents=True)
        (self.root / "logs").mkdir()
        shutil.copy(ROOT / "deploy" / "healthcheck.sh", self.root / "deploy" / "healthcheck.sh")
        alert = self.root / "deploy" / "alert.sh"
        alert.write_text('#!/usr/bin/env bash\necho "alert $*" >> "$CALLS"\n')
        alert.chmod(0o755)
        shims = tmp / "shims"
        shims.mkdir()
        (shims / "systemctl").write_text('#!/usr/bin/env bash\nstate=$(cat "$BOT_STATE")\n'
                                         '[ "$1" = is-active ] && [ "$2" = --quiet ] && { [ "$state" = active ]; exit; }\n'
                                         'echo "$state"\n')
        (shims / "systemctl").chmod(0o755)
        self.state = tmp / "bot_state"
        self.state.write_text("active")
        self.env = dict(os.environ, PATH=f"{shims}:{os.environ['PATH']}", CALLS=str(self.calls), BOT_STATE=str(self.state))
        self.calls.write_text("")

    def rows(self, *rows):
        with open(self.root / "logs" / "swan_actions.jsonl", "a") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    def run(self):
        subprocess.run(["bash", "deploy/healthcheck.sh"], cwd=self.root, env=self.env, check=True, timeout=30)
        return [x for x in self.calls.read_text().splitlines() if x]

    def health(self):
        return (self.root / "data" / "health_state").read_text()


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


def test_syntax():
    assert subprocess.run(["bash", "-n", str(ROOT / "deploy" / "healthcheck.sh")]).returncode == 0


def test_a_recent_reply_is_healthy(box):
    box.rows(dict(ts=iso(2), act="reply", live=True, username="v1"))
    assert box.run() == [] and box.health() == ""


def test_likes_follows_and_the_swarm_do_not_count_as_writing(box):
    box.rows(dict(ts=iso(20), act="reply", live=True, username="v1"),
             dict(ts=iso(1), act="like", live=True, role="booster"),
             dict(ts=iso(1), act="follow", live=True),
             dict(ts=iso(1), act="like_failed", live=True),
             dict(ts=iso(1), act="repost", live=True, role="swarm", owner="minhnguyenhoang"),
             dict(ts=iso(0), act="wait", why="no_voice"))
    calls = box.run()
    assert len(calls) == 1 and calls[0].startswith("alert BOT NOT WRITING: no post or reply for 20 min"), calls
    assert box.health().startswith("BOT NOT WRITING")


def test_a_problem_is_alerted_once_then_hourly_then_its_recovery(box):
    box.rows(dict(ts=iso(30), act="repost", live=True, username="v1"))
    assert len(box.run()) == 1
    assert len(box.run()) == 1, "the minutes in the text changed, the problem did not: no second alert"
    alerted = box.root / "data" / "health_alerted"
    ts, kind = alerted.read_text().split("\n")[:2]
    assert kind == "BOT NOT WRITING"
    alerted.write_text(f"{int(ts) - 3601}\n{kind}\n")
    assert len(box.run()) == 2, "an hour on, still not writing: a reminder"
    box.rows(dict(ts=iso(0), act="reply", live=True, username="v1"))
    calls = box.run()
    assert calls[-1] == "alert recovered: bot running and writing again" and box.health() == ""
    assert not alerted.exists()


def test_a_new_kind_of_problem_is_alerted_at_once(box):
    box.rows(dict(ts=iso(30), act="reply", live=True, username="v1"))
    box.run()
    box.state.write_text("failed")
    calls = box.run()
    assert len(calls) == 2 and calls[-1] == "alert BOT OFFLINE: swan-bot is failed"


def test_the_threshold_can_be_set(box):
    box.rows(dict(ts=iso(10), act="reply", live=True, username="v1"))
    assert box.run() == []
    box.env["SWAN_NO_WRITE_ALERT_S"] = "300"
    assert len(box.run()) == 1


def test_the_threshold_is_read_from_dot_env(box):
    """systemd does not load .env for the timer: the script reads it, like HEALTHCHECK_PING_URL."""
    box.rows(dict(ts=iso(20), act="reply", live=True, username="v1"))
    (box.root / ".env").write_text("CTN_SIDE=no\nSWAN_NO_WRITE_ALERT_S=1800\n")
    assert box.run() == [] and box.health() == "", "20 min without a write is fine at 30 min"
