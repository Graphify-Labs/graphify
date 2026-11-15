"""Hooks must rebuild once after every git operation that changes the tree (#4490).

Each test counts the background-rebuild launch line in git's output (hooks
write to stderr). git leaves CHERRY_PICK_HEAD, sequencer/ and rebase-merge/ on
disk while post-commit and post-rewrite run, so cherry-pick and rebase never
rebuilt. Real-build tests wait for the detached rebuild before reading the graph.
"""
import json
import os
import subprocess
import sys
import time

import pytest

from graphify.hooks import install
from tests.test_hooks import _LAUNCH_LINE, _SH_ONLY


class Repo:
    def __init__(self, path, home):
        self.path = path
        path.mkdir()
        self.env = {
            **os.environ, "HOME": str(home),
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t.co",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t.co",
            "GIT_EDITOR": "true",
        }
        self.quiet = {**self.env, "GRAPHIFY_SKIP_HOOK": "1"}

    def git(self, *args, quiet=False, check=True):
        return subprocess.run(
            ["git", *args], cwd=self.path, capture_output=True, text=True,
            env=self.quiet if quiet else self.env, check=check,
        )

    def launches(self, *args, check=True):
        out = self.git(*args, check=check)
        return (out.stdout + out.stderr).count(_LAUNCH_LINE)

    def write(self, name, text):
        (self.path / name).write_text(text, encoding="utf-8")

    def commit(self, name, text, msg):
        self.write(name, text)
        self.git("add", name)
        self.git("commit", "-qm", msg, quiet=True)

    def build(self):
        subprocess.run([sys.executable, "-m", "graphify", "update", "."], cwd=self.path,
                       env=self.env, check=True, capture_output=True)

    def labels(self):
        graph = json.loads((self.path / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
        return {n["label"] for n in graph["nodes"]}


def _settle(repo, home, timeout=60):
    """Wait until the detached rebuild is done: log stable, no lock or pending files."""
    log, out = home / ".cache" / "graphify-rebuild.log", repo.path / "graphify-out"
    t0 = time.time()
    while time.time() - t0 < 5 and not log.exists():
        time.sleep(0.1)
    if not log.exists():
        return  # nothing was launched; the caller's assertions say what was expected
    last = (-1, 0.0)
    while time.time() - t0 < timeout:
        size = log.stat().st_size
        busy = any((out / n).exists() for n in (".rebuild.lock", ".pending_changes", ".pending_full"))
        if size != last[0]:
            last = (size, time.time())
        elif not busy and time.time() - last[1] > 2:
            return
        time.sleep(0.2)
    pytest.fail("the background rebuild did not settle")


@pytest.fixture
def repo(tmp_path):
    r = Repo(tmp_path / "repo", tmp_path)
    r.git("init", "-q", "-b", "main")
    (r.path / "graphify-out").mkdir()
    r.write("graphify-out/graph.json", "{}")
    r.commit("a.py", "def a(): pass\n", "init")
    install(r.path)
    return r


def _built_repo(tmp_path):
    """A repo with a real first build and the hooks installed."""
    r = Repo(tmp_path / "repo", tmp_path)
    r.git("init", "-q", "-b", "main")
    r.commit("base.py", "".join(f"def b{i}(x):\n    return x\n\n" for i in range(6)), "init")
    r.commit("shared.py", "def s(): return 0\n", "shared")
    r.build()
    install(r.path)
    return r


@_SH_ONLY
def test_control_plain_commit_rebuilds_once(repo):
    repo.write("b.py", "def b(): pass\n")
    repo.git("add", "b.py")
    assert repo.launches("commit", "-qm", "b") == 1


@_SH_ONLY
def test_single_cherry_pick_rebuilds_once(repo):
    repo.git("checkout", "-qb", "side", quiet=True)
    repo.commit("cp.py", "def cp(): pass\n", "cp")
    repo.git("checkout", "-q", "main", quiet=True)
    assert repo.launches("cherry-pick", "side") == 1


@_SH_ONLY
def test_range_cherry_pick_rebuilds_once(repo):
    repo.git("checkout", "-qb", "side", quiet=True)
    for i in range(3):
        repo.commit(f"r{i}.py", f"def r{i}(): pass\n", f"r{i}")
    repo.git("checkout", "-q", "main", quiet=True)
    assert repo.launches("cherry-pick", "side~3..side") == 1


@_SH_ONLY
def test_rebase_rebuilds_once(repo):
    repo.git("checkout", "-qb", "feat", quiet=True)
    repo.commit("f.py", "def f(): pass\n", "f")
    repo.git("checkout", "-q", "main", quiet=True)
    repo.commit("m.py", "def m(): pass\n", "m")
    repo.git("checkout", "-q", "feat", quiet=True)
    assert repo.launches("rebase", "main") == 1


@_SH_ONLY
def test_pull_rebase_rebuilds_once(repo, tmp_path):
    clone = Repo(tmp_path / "clone", tmp_path)
    clone.git("clone", "-q", str(repo.path), ".")  # into the empty dir Repo made
    (clone.path / "graphify-out").mkdir()  # the graph is untracked, so a clone has none
    clone.write("graphify-out/graph.json", "{}")
    install(clone.path)
    repo.commit("up.py", "def up(): pass\n", "up")
    clone.commit("lo.py", "def lo(): pass\n", "lo")
    assert clone.launches("pull", "--rebase") == 1


@_SH_ONLY
def test_amend_rebuilds_exactly_once(repo):
    # amend a non-root commit: on a root commit the hook has no HEAD~1 to diff
    repo.commit("b.py", "def b(): pass\n", "b")
    repo.write("a.py", "def a(): return 1\n")
    repo.git("add", "a.py")
    assert repo.launches("commit", "-q", "--amend", "-m", "amended") == 1


@_SH_ONLY
def test_conflicted_rebase_continues_and_rebuilds_once(repo):
    repo.git("checkout", "-qb", "feat", quiet=True)
    repo.commit("a.py", "def a(): return 'feat'\n", "feat edit")
    repo.git("checkout", "-q", "main", quiet=True)
    repo.commit("a.py", "def a(): return 'main'\n", "main edit")
    repo.git("checkout", "-q", "feat", quiet=True)
    assert repo.launches("rebase", "main", check=False) == 0  # paused on conflict
    repo.write("a.py", "def a(): return 'both'\n")
    repo.git("add", "a.py")
    out = repo.git("rebase", "--continue")  # must not be blocked by a hook
    assert (out.stdout + out.stderr).count(_LAUNCH_LINE) == 1
    assert not (repo.path / ".git" / "rebase-merge").exists()


@_SH_ONLY
def test_range_cherry_pick_lands_every_new_function(tmp_path):
    r = _built_repo(tmp_path)
    r.git("checkout", "-qb", "side", quiet=True)
    for i in (1, 2, 3):
        r.commit(f"f{i}.py", f"def new_fn{i}(x):\n    return x\n", f"c{i}")
    r.git("checkout", "-q", "main", quiet=True)
    r.git("cherry-pick", "side~3..side")
    _settle(r, tmp_path)
    assert {"new_fn1()", "new_fn2()", "new_fn3()"} <= r.labels()


@_SH_ONLY
def test_skip_mid_range_rebuilds_the_picks_that_landed(tmp_path):
    r = _built_repo(tmp_path)
    r.git("checkout", "-qb", "side", quiet=True)
    r.commit("fs1.py", "def fs_one(): pass\n", "c1")
    r.write("fs2.py", "def fs_two(): pass\n")
    r.write("shared.py", "def s(): return 2\n")
    r.git("add", ".")
    r.git("commit", "-qm", "c2", quiet=True)
    r.commit("fs3.py", "def fs_three(): pass\n", "c3")
    r.git("checkout", "-q", "main", quiet=True)
    r.commit("shared.py", "def s(): return 1\n", "main edit")
    r.git("cherry-pick", "side~3..side", check=False)  # pauses on c2
    assert r.launches("cherry-pick", "--skip") == 1
    _settle(r, tmp_path)
    labels = r.labels()
    assert {"fs_one()", "fs_three()"} <= labels and "fs_two()" not in labels


@_SH_ONLY
def test_revert_range_rebuilds_once_and_removes_the_functions(tmp_path):
    """Pins one rebuild per revert range. This is not a v8 bug: v8 rebuilt after
    each revert, three times. A revert range uses the same sequencer/ as a pick
    range, so it follows the same skip-until-the-last-step rule."""
    r = Repo(tmp_path / "repo", tmp_path)
    r.git("init", "-q", "-b", "main")
    r.commit("base.py", "def base(): pass\n", "init")
    for i, name in enumerate(("fr_one", "fr_two", "fr_three"), 1):
        r.commit(f"fr{i}.py", f"def {name}(): pass\n", name)
    r.build()
    install(r.path)
    assert r.launches("revert", "--no-edit", "HEAD~3..HEAD") == 1
    _settle(r, tmp_path)
    assert not {"fr_one()", "fr_two()", "fr_three()"} & r.labels()


@_SH_ONLY
def test_tracked_graph_range_pick_with_conflict_completes(tmp_path):
    """With graph.json tracked, a rebuild between picks would dirty it and git would
    refuse the next pick that touches it ("local changes would be overwritten")."""
    r = Repo(tmp_path / "repo", tmp_path)
    r.git("init", "-q", "-b", "main")
    (r.path / "graphify-out").mkdir()
    r.write("graphify-out/graph.json", "{}")
    r.commit("shared.py", "def s(): return 0\n", "init")
    r.git("add", "-f", "graphify-out/graph.json")
    r.git("commit", "-qm", "track", quiet=True)
    install(r.path)
    r.git("checkout", "-qb", "side", quiet=True)
    r.commit("n1.py", "def n1(): pass\n", "c1")
    r.commit("shared.py", "def s(): return 2\n", "c2")
    r.write("graphify-out/graph.json", '{"teammate": true}')
    r.git("add", "-f", "graphify-out/graph.json")
    r.git("commit", "-qm", "c3", quiet=True)
    r.git("checkout", "-q", "main", quiet=True)
    r.commit("shared.py", "def s(): return 1\n", "main edit")
    r.git("cherry-pick", "side~3..side", check=False)  # pauses on c2
    r.write("shared.py", "def s(): return 3\n")
    r.git("add", "shared.py")
    out = r.git("cherry-pick", "--continue", check=False)
    assert out.returncode == 0, out.stdout + out.stderr
    assert not (r.path / ".git" / "sequencer").exists()
    _settle(r, tmp_path)  # cleanup only: lets the rebuild after the last pick finish before tmp_path goes


@_SH_ONLY
def test_abandoned_range_pick_does_not_silence_later_commits(repo):
    """git reset --hard (not --abort) leaves sequencer/ behind. Trusting its pending steps
    would skip every later commit's rebuild; the hook must see it is stale."""
    repo.git("checkout", "-qb", "side", quiet=True)
    repo.commit("n1.py", "def n1(): pass\n", "c1")
    repo.commit("a.py", "def a(): return 2\n", "c2")
    repo.commit("n3.py", "def n3(): pass\n", "c3")
    repo.git("checkout", "-q", "main", quiet=True)
    repo.commit("a.py", "def a(): return 1\n", "main edit")
    repo.git("cherry-pick", "side~3..side", check=False)  # pauses on c2
    repo.git("reset", "-q", "--hard", "HEAD")
    if not (repo.path / ".git" / "sequencer").exists():
        pytest.skip("this git removes sequencer/ on reset --hard, so there is nothing stale to test")
    repo.write("z.py", "def z(): pass\n")
    repo.git("add", "z.py")
    assert repo.launches("commit", "-qm", "z") == 1
