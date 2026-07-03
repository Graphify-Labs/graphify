"""`graphify merge-driver` must stamp its output like every other graph.json
writer (d1692f4's stamp_graph_metadata() chokepoint), so a merge-committed
graph.json still carries generated_at/indexed_repo_root for check_staleness.

Unlike the other writers, merge-driver has no natural "root" argument: git
invokes it as `graphify merge-driver %O %A %B` with three throwaway temp file
paths, not the real graphify-out/graph.json location. The fix resolves the
indexed repo root via `git rev-parse --show-toplevel`, relying on git running
merge drivers with cwd set to the top of the work tree - so these tests set
`cwd` to the repo being merged, exactly like a real git merge invocation.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PYTHON = sys.executable


def _run(args, cwd):
    return subprocess.run([PYTHON, "-m", "graphify"] + args, cwd=cwd,
                          capture_output=True, text=True)


def _init_repo_with_one_commit(repo_dir: Path) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(repo_dir)], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "Test"], check=True)
    (repo_dir / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo_dir), "add", "a.py"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-q", "-m", "init"], check=True)


def _write_graph(p: Path, node_id: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [{"id": node_id}], "links": [],
    }))


def test_merge_driver_stamps_generated_at_and_indexed_repo_root(tmp_path):
    """Reviewer repro: the merge-driver writer (__main__.py) was the last
    graph.json writer left unstamped after d1692f4. Its output must gain
    generated_at and an indexed_repo_root resolved to the repo git is merging
    in - not left absent, and not guessed from the (unrelated) temp file
    paths git passes for base/current/other."""
    repo_dir = tmp_path / "repo"
    _init_repo_with_one_commit(repo_dir)

    # base/current/other live OUTSIDE the repo, like git's real temp files do.
    tmp_side = tmp_path / "merge-tmp"
    base = tmp_side / "base.json"
    current = tmp_side / "current.json"
    other = tmp_side / "other.json"
    _write_graph(base, "x")
    _write_graph(current, "x")
    _write_graph(other, "y")

    r = _run(
        ["merge-driver", str(base), str(current), str(other)],
        cwd=repo_dir,
    )
    assert r.returncode == 0, f"merge-driver failed: {r.stderr}"

    data = json.loads(current.read_text(encoding="utf-8"))
    ids = {n["id"] for n in data["nodes"]}
    assert ids == {"x", "y"}
    assert "generated_at" in data, (
        "merge-driver must stamp generated_at just like every other writer"
    )
    assert data.get("indexed_repo_root") == str(repo_dir.resolve()), (
        "merge-driver must record the repo git is merging in (its cwd), not "
        "the throwaway base/current/other temp file locations"
    )


def test_merge_driver_falls_back_to_current_side_root_outside_git(tmp_path):
    """When merge-driver somehow runs outside a git work tree (rev-parse
    --show-toplevel fails), it must not fabricate a root out of thin air -
    it falls back to whatever indexed_repo_root the current side already
    carried, so a legitimately-rooted graph doesn't get silently rebased
    onto some throwaway cwd."""
    outside_dir = tmp_path / "not-a-repo"
    outside_dir.mkdir()

    tmp_side = tmp_path / "merge-tmp"
    prior_root = tmp_path / "prior-root"
    prior_root.mkdir()
    base = tmp_side / "base.json"
    current = tmp_side / "current.json"
    other = tmp_side / "other.json"
    _write_graph(base, "x")
    current.parent.mkdir(parents=True, exist_ok=True)
    current.write_text(json.dumps({
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [{"id": "x"}], "links": [],
        "indexed_repo_root": str(prior_root.resolve()),
    }))
    _write_graph(other, "y")

    r = _run(
        ["merge-driver", str(base), str(current), str(other)],
        cwd=outside_dir,
    )
    assert r.returncode == 0, f"merge-driver failed: {r.stderr}"

    data = json.loads(current.read_text(encoding="utf-8"))
    assert "generated_at" in data
    assert data.get("indexed_repo_root") == str(prior_root.resolve())
