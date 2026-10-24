"""todo/34 item 6: deploy/update.sh checks the new commit in a throwaway worktree before the box moves onto it.

Offline and fast: a bare "origin", a "box" clone and a "dev" clone in tmp_path. The box runs the real update.sh;
sudo, systemctl and the venv's python/pip are shims on PATH that log to calls.log, and each commit carries stub
check.sh / alert.sh / install.sh (the worktree runs the candidate commit's own check.sh, so a commit decides whether
its check passes, fails or hangs)."""
import json
import os
import pathlib
import shutil
import signal
import subprocess
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
UPDATE_SH = ROOT / "deploy" / "update.sh"

CHECK_OK = '#!/usr/bin/env bash\ncd "$(dirname "$0")/.."\necho "check pwd=${PWD##*/} skip=${SKIP_TESTS:-} py=${PY:+set}" >> "$CALLS"\necho "checks ok"\n'
CHECK_FAIL = CHECK_OK.replace('echo "checks ok"', 'echo "boom: import failed"; exit 1')
CHECK_SLOW = CHECK_OK.replace('echo "checks ok"', 'echo "check started" >> "$CALLS"; sleep 60')
ALERT = '#!/usr/bin/env bash\necho "alert $*" >> "$CALLS"\n'
INSTALL = ('#!/usr/bin/env bash\necho "install $*" >> "$CALLS"\n'
           '[ -e "$BLOCK" ] && { echo "install blocked" >> "$CALLS"; sleep 60; }\nexit 0\n')


def sh(*args, cwd, env=None, check=True):
    e = dict(os.environ, GIT_AUTHOR_NAME="Dev", GIT_AUTHOR_EMAIL="d@x", GIT_COMMITTER_NAME="Dev", GIT_COMMITTER_EMAIL="d@x")
    e.update(env or {})
    return subprocess.run(args, cwd=cwd, env=e, check=check, capture_output=True, text=True).stdout.strip()


class Rig:
    def __init__(self, tmp):
        self.tmp = tmp
        self.origin, self.dev, self.box = tmp / "origin.git", tmp / "dev", tmp / "box"
        self.calls = tmp / "calls.log"
        self.calls.write_text("")
        self.started = tmp / "bot_started"            # what `systemctl show swan-bot -p ActiveEnterTimestamp` answers
        self.started.write_text("Thu 2020-01-01 00:00:00 UTC\n")
        self.block = tmp / "block"                     # exists -> stub install.sh hangs (a run killed mid-apply)
        sh("git", "init", "-q", "--bare", "-b", "main", str(self.origin), cwd=tmp)
        sh("git", "clone", "-q", str(self.origin), str(self.dev), cwd=tmp)
        for name, text in (("check.sh", CHECK_OK), ("alert.sh", ALERT), ("install.sh", INSTALL)):
            self.write(f"deploy/{name}", text, mode=0o755)
        shutil.copy(UPDATE_SH, self.dev / "deploy" / "update.sh")
        self.write(".gitignore", ".venv/\ndata/\nlogs/\n")
        self.write("requirements.txt", "# none\n")
        self.write("src/mod.py", "X = 1\n")
        self.write("docs/a.md", "a\n")
        self.push("initial")
        sh("git", "clone", "-q", str(self.origin), str(self.box), cwd=tmp)
        venv = self.box / ".venv" / "bin"
        venv.mkdir(parents=True)
        for exe in ("python", "pip"):
            (venv / exe).write_text(f'#!/usr/bin/env bash\necho "{exe} $*" >> "$CALLS"\n')
            (venv / exe).chmod(0o755)
        shims = tmp / "shims"
        shims.mkdir()
        (shims / "sudo").write_text('#!/usr/bin/env bash\necho "sudo $*" >> "$CALLS"\nexec "$@"\n')
        (shims / "systemctl").write_text(
            '#!/usr/bin/env bash\n'
            'if [ "$1" = show ]; then cat "$STARTED"; exit 0; fi\n'
            'echo "systemctl $*" >> "$CALLS"\n')
        for f in shims.iterdir():
            f.chmod(0o755)
        self.env = dict(PATH=f"{shims}:{os.environ['PATH']}", CALLS=str(self.calls), STARTED=str(self.started),
                        BLOCK=str(self.block), SWAN_UPDATE_LOCK=str(tmp / "lock"))
        self.deploys = self.box / "logs" / "deploys.jsonl"
        # the box starts out deployed: one ok record for the initial commit (as after install.sh + the first tick)
        (self.box / "logs").mkdir()
        self.record_line(self.head(), "ok")

    def write(self, rel, text, mode=0o644):
        p = self.dev / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        p.chmod(mode)

    def push(self, msg):
        sh("git", "add", "-A", cwd=self.dev)
        sh("git", "commit", "-q", "-m", msg, cwd=self.dev)
        sh("git", "push", "-q", "origin", "main", cwd=self.dev)
        return sh("git", "rev-parse", "HEAD", cwd=self.dev)

    def head(self):
        return sh("git", "rev-parse", "HEAD", cwd=self.box)

    def record_line(self, sha, result, old=""):
        with open(self.box / "logs" / "deploys.jsonl", "a") as f:
            f.write(json.dumps(dict(ts="2026-10-23T00:00:00Z", old=old, new=sha, result=result)) + "\n")

    def run(self, **kw):
        return subprocess.run(["bash", "deploy/update.sh"], cwd=self.box, env=dict(os.environ, **self.env),
                              capture_output=True, text=True, timeout=60, **kw)

    def popen(self):
        return subprocess.Popen(["bash", "deploy/update.sh"], cwd=self.box, env=dict(os.environ, **self.env),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)

    def log(self):
        return self.calls.read_text().splitlines()

    def records(self):
        return [json.loads(x) for x in self.deploys.read_text().splitlines()]

    def wait_for(self, text, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            if any(text in line for line in self.log()):
                return
            time.sleep(0.05)
        raise AssertionError(f"never saw {text!r} in {self.log()}")

    def worktrees(self):
        return [x for x in sh("git", "worktree", "list", "--porcelain", cwd=self.box).splitlines() if x.startswith("worktree ")]


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def restarts(rig):
    return [x for x in rig.log() if x.startswith("systemctl try-restart")]


def alerts(rig):
    return [x for x in rig.log() if x.startswith("alert ")]


def test_syntax():
    assert subprocess.run(["bash", "-n", str(UPDATE_SH)]).returncode == 0


def test_nothing_to_do(rig):
    before = rig.head()
    r = rig.run()
    assert r.returncode == 0
    assert rig.head() == before
    assert rig.log() == []                       # no check, no restart, no alert
    assert len(rig.records()) == 1               # and no new record


def test_good_commit_deploys(rig):
    old = rig.head()
    rig.write("src/mod.py", "X = 2\n")
    new = rig.push("Bump X")
    r = rig.run()
    assert r.returncode == 0, r.stderr
    assert rig.head() == new
    log = rig.log()
    assert any(x.startswith("check pwd=deploy-check skip=1 py=set") for x in log)    # checked in the worktree, tests skipped
    assert restarts(rig) == ["systemctl try-restart swan-bot swan-blue"]
    assert not any(x.startswith("install ") for x in log)                           # no unit file changed
    rec = rig.records()[-1]
    assert (rec["old"], rec["new"], rec["result"]) == (old, new, "ok")
    assert alerts(rig) == [f"alert deployed {new[:7]} Dev: Bump X"]
    assert log.index(next(x for x in log if x.startswith("check "))) < log.index("systemctl try-restart swan-bot swan-blue")
    assert rig.worktrees() == [f"worktree {rig.box}"]                               # the throwaway worktree is gone
    assert not (rig.box / "data" / "deploy-check").exists()
    assert rig.run().returncode == 0 and len(alerts(rig)) == 1                      # next tick: nothing to do


def test_unit_file_change_runs_install_units_only(rig):
    rig.write("deploy/swan-x.service", "[Service]\n")
    rig.push("new unit")
    assert rig.run().returncode == 0
    assert "sudo deploy/install.sh --units-only" in rig.log()
    assert "install --units-only" in rig.log()
    assert restarts(rig)                          # deploy/ is code


def test_docs_and_lab_only_pushes_do_not_restart(rig):
    rig.write("docs/a.md", "b\n")
    rig.write("todo/1.md", "t\n")
    rig.write("content/lab/s.toml", "x = 1\n")
    rig.write("src/swan_dash/build.py", "x = 1\n")        # the dashboard runs from its own timer
    new = rig.push("docs, lab and dashboard")
    assert rig.run().returncode == 0
    assert rig.head() == new and rig.records()[-1]["result"] == "ok"
    assert restarts(rig) == [] and alerts(rig)    # deployed, but the bot was not restarted
    rig.write("content/facts.toml", "x = 1\n")
    rig.push("facts")
    assert rig.run().returncode == 0 and len(restarts(rig)) == 1


def test_requirements_change_is_installed_before_the_check(rig):
    rig.write("requirements.txt", "six\n")
    rig.push("dep")
    assert rig.run().returncode == 0
    log = rig.log()
    pip = next(i for i, x in enumerate(log) if x.startswith("pip install -q -r") and x.endswith("deploy-check/requirements.txt"))
    assert pip < next(i for i, x in enumerate(log) if x.startswith("check "))


def test_failing_check_leaves_the_old_commit_alerts_once_then_a_fix_deploys(rig):
    old = rig.head()
    rig.write("deploy/check.sh", CHECK_FAIL, 0o755)
    rig.write("src/mod.py", "X = 3\n")
    bad = rig.push("Break it")
    r = rig.run()
    assert r.returncode == 1
    assert rig.head() == old                      # never moved
    assert restarts(rig) == []
    rec = rig.records()[-1]
    assert (rec["old"], rec["new"], rec["result"]) == (old, bad, "failed")
    (a,) = alerts(rig)
    assert a.startswith(f"alert DEPLOY FAILED, staying on {old[:7]}") and "Break it" in a and "boom: import failed" in a
    assert rig.worktrees() == [f"worktree {rig.box}"]
    assert (rig.box / "logs" / "deploy_failed_sha").read_text().strip() == bad
    # the next ticks skip that sha silently: no second check, record or alert
    n_calls, n_rec = len(rig.log()), len(rig.records())
    for _ in range(2):
        assert rig.run().returncode == 0
    assert len(rig.log()) == n_calls and len(rig.records()) == n_rec and rig.head() == old
    # a newer push is tried again, and a fix deploys
    rig.write("deploy/check.sh", CHECK_OK, 0o755)
    fixed = rig.push("Fix it")
    assert rig.run().returncode == 0
    assert rig.head() == fixed and rig.records()[-1]["result"] == "ok"
    assert len(restarts(rig)) == 1 and len(alerts(rig)) == 2
    assert not (rig.box / "logs" / "deploy_failed_sha").exists()


def test_killed_during_the_check_leaves_the_old_commit(rig):
    old = rig.head()
    rig.write("deploy/check.sh", CHECK_SLOW, 0o755)
    new = rig.push("Slow check")
    p = rig.popen()
    rig.wait_for("check started")
    assert (rig.box / "data" / "deploy-check").exists()      # the check is running in the worktree
    assert rig.head() == old                                  # while the live tree is untouched
    os.killpg(p.pid, signal.SIGTERM)                          # systemd stop: the whole cgroup
    p.communicate(timeout=20)
    assert rig.head() == old and len(rig.records()) == 1 and restarts(rig) == [] and alerts(rig) == []
    assert not (rig.box / "data" / "deploy-check").exists()  # the trap cleaned up
    assert rig.worktrees() == [f"worktree {rig.box}"]
    # a fixed commit then deploys cleanly
    rig.write("deploy/check.sh", CHECK_OK, 0o755)
    fixed = rig.push("Fast check")
    assert rig.run().returncode == 0 and rig.head() == fixed and new != fixed


def test_sigkill_during_the_check_is_cleaned_up_by_the_next_run(rig):
    old = rig.head()
    rig.write("deploy/check.sh", CHECK_SLOW, 0o755)
    rig.push("Slow check")
    p = rig.popen()
    rig.wait_for("check started")
    os.killpg(p.pid, signal.SIGKILL)                          # no trap can run
    p.communicate(timeout=20)
    assert rig.head() == old and len(rig.records()) == 1 and restarts(rig) == []
    assert (rig.box / "data" / "deploy-check").exists() and len(rig.worktrees()) == 2     # leftover
    rig.write("deploy/check.sh", CHECK_OK, 0o755)
    fixed = rig.push("Fast check")
    assert rig.run().returncode == 0 and rig.head() == fixed
    assert rig.worktrees() == [f"worktree {rig.box}"] and not (rig.box / "data" / "deploy-check").exists()


def test_killed_after_the_reset_heals_on_the_next_tick(rig):
    old = rig.head()
    rig.write("deploy/swan-x.service", "[Service]\n")
    rig.write("src/mod.py", "X = 4\n")
    new = rig.push("Code and unit")
    rig.block.write_text("")                                   # the units-only step hangs: killed after the reset
    p = rig.popen()
    rig.wait_for("install blocked")
    os.killpg(p.pid, signal.SIGKILL)
    p.communicate(timeout=20)
    assert rig.head() == new                                   # the tree moved...
    assert len(rig.records()) == 1 and alerts(rig) == [] and restarts(rig) == []    # ...but nothing was recorded
    rig.block.unlink()
    rig.calls.write_text("")
    r = rig.run()                                              # next tick: old == new, the record is missing
    assert r.returncode == 0, r.stderr
    rec = rig.records()[-1]
    assert (rec["old"], rec["new"], rec["result"], rec["note"]) == (old, new, "ok", "catch-up")
    assert alerts(rig) == [f"alert deployed {new[:7]} Dev: Code and unit (catch-up)"]
    assert "install --units-only" in rig.log()                 # the unit file the killed run never installed
    assert len(restarts(rig)) == 1                             # the bot (started 2020) predates the tree move
    rig.calls.write_text("")
    assert rig.run().returncode == 0 and rig.log() == [] and rig.records()[-1] == rec    # and it is done


def test_catch_up_does_not_restart_a_bot_that_already_runs_the_new_tree(rig):
    rig.write("src/mod.py", "X = 5\n")
    new = rig.push("Code")
    sh("git", "pull", "-q", "origin", "main", cwd=rig.box)     # a manual deploy on the box, no record
    rig.started.write_text("Fri 2099-01-01 00:00:00 UTC\n")    # and the bot was restarted after it
    assert rig.run().returncode == 0
    assert rig.records()[-1]["new"] == new and rig.records()[-1]["note"] == "catch-up"
    assert restarts(rig) == [] and len(alerts(rig)) == 1


def test_catch_up_does_not_restart_for_docs_or_a_stopped_bot(rig):
    rig.write("docs/a.md", "c\n")
    rig.push("docs")
    sh("git", "pull", "-q", "origin", "main", cwd=rig.box)
    assert rig.run().returncode == 0 and restarts(rig) == [] and rig.records()[-1]["note"] == "catch-up"
    rig.write("src/mod.py", "X = 6\n")
    rig.push("Code")
    sh("git", "pull", "-q", "origin", "main", cwd=rig.box)
    rig.started.write_text("\n")                               # swan-bot inactive: a deliberate stop stays stopped
    assert rig.run().returncode == 0 and restarts(rig) == []


def test_old_style_failed_record_does_not_trigger_a_catch_up(rig):
    rig.record_line("f" * 40, "failed", old=rig.head())        # a rollback record from the previous update.sh
    assert rig.run().returncode == 0 and rig.log() == [] and len(rig.records()) == 2
