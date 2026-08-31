"""#2316: `graphify update <target>` must write manifest.json into the TARGET's
graphify-out/, not the process CWD's.

`_rebuild_code` computes ``out = watch_path / _GRAPHIFY_OUT`` and routes every
other artifact through it, but the three ``save_manifest`` calls omitted
``manifest_path=`` and so fell through to ``detect._MANIFEST_PATH`` — a
module-import-time constant resolved against the CWD. Running `update` on
project B from project A therefore wrote B's manifest into A's output dir and
left B with none.

Because ``save_manifest`` also *reads* that path and full-scan callers pass
``scan_corpus`` (#1908 pruning), A's own rows were pruned as "not in the scan
corpus" and destroyed — the CWD project loses its incremental baseline too.
"""

import json
import os
from pathlib import Path

import pytest


def _corpus(base: Path, name: str, func: str) -> Path:
    d = base / name
    d.mkdir()
    (d / f"{name}_file.py").write_text(
        f"def {func}():\n    return helper_{func}()\n\n"
        f"def helper_{func}():\n    return 1\n",
        encoding="utf-8",
    )
    return d


@pytest.fixture()
def two_projects(tmp_path):
    """A CWD project and a separate target project, with the CWD set to the former."""
    proj_a = _corpus(tmp_path, "proja", "alpha")
    proj_b = _corpus(tmp_path, "projb", "beta")
    return proj_a, proj_b


@pytest.mark.parametrize("no_cluster", [False, True], ids=["clustered", "no-cluster"])
def test_manifest_lands_in_the_target_not_the_cwd(two_projects, monkeypatch, no_cluster):
    """Covers the clustered write site and the --no-cluster write site."""
    from graphify.watch import _rebuild_code

    proj_a, proj_b = two_projects
    monkeypatch.chdir(proj_a)

    assert _rebuild_code(proj_b, acquire_lock=False, no_cluster=no_cluster) is True

    target_manifest = proj_b / "graphify-out" / "manifest.json"
    cwd_manifest = proj_a / "graphify-out" / "manifest.json"

    assert target_manifest.exists(), (
        "manifest.json must land next to the graph it describes, in the target's "
        f"graphify-out/ (#2316); {target_manifest} is missing"
    )
    assert not cwd_manifest.exists(), (
        "an update targeting another project must not create a manifest in the "
        f"CWD project; found {cwd_manifest}"
    )

    rows = json.loads(target_manifest.read_text(encoding="utf-8"))
    assert rows, "target manifest is empty — nothing for the next incremental run"
    assert any("projb_file.py" in k for k in rows), (
        f"target manifest should describe the target's files; got {sorted(rows)}"
    )


def test_second_run_reaches_the_same_topology_early_return(two_projects, monkeypatch, capsys):
    """The unchanged-topology early return is a third, separate save_manifest site.

    Running twice with no edits takes it, so the manifest must still land in the
    target on that path.
    """
    from graphify.watch import _rebuild_code

    proj_a, proj_b = two_projects
    monkeypatch.chdir(proj_a)

    assert _rebuild_code(proj_b, acquire_lock=False) is True
    target_manifest = proj_b / "graphify-out" / "manifest.json"
    # Remove it so a second write is the only thing that can recreate it, which
    # keeps this test honest about which run produced the file.
    target_manifest.unlink(missing_ok=True)

    capsys.readouterr()
    assert _rebuild_code(proj_b, acquire_lock=False) is True

    # Guard against this test silently drifting off the branch it exists to
    # cover: without this the second run could take the ordinary clustered
    # path and the assertions below would pass for the wrong reason.
    assert "No code-graph topology changes detected" in capsys.readouterr().out, (
        "second run did not take the unchanged-topology early return, so this "
        "test no longer covers that save_manifest site"
    )

    assert target_manifest.exists(), (
        "the unchanged-topology early-return path must also write the manifest "
        "into the target's graphify-out/ (#2316)"
    )
    assert not (proj_a / "graphify-out" / "manifest.json").exists(), (
        "the unchanged-topology path wrote the manifest into the CWD project"
    )


def test_update_does_not_destroy_the_cwd_projects_own_manifest(two_projects, monkeypatch):
    """The severe half of #2316: it is data loss, not just a misplaced file.

    save_manifest read-modify-writes the same path and full-scan callers pass
    scan_corpus, so the CWD project's rows were pruned as out-of-corpus and
    overwritten with the target's. Both projects then need a full rescan.
    """
    from graphify.watch import _rebuild_code

    proj_a, proj_b = two_projects
    monkeypatch.chdir(proj_a)

    # Give proj_a a legitimate manifest of its own, the way `update .` would.
    assert _rebuild_code(Path("."), acquire_lock=False) is True
    own_manifest = proj_a / "graphify-out" / "manifest.json"
    before = own_manifest.read_text(encoding="utf-8")
    assert "proja_file.py" in before, "precondition: proj_a must have its own rows"

    assert _rebuild_code(proj_b, acquire_lock=False) is True

    after = own_manifest.read_text(encoding="utf-8")
    assert after == before, (
        "updating another project must leave the CWD project's manifest untouched; "
        f"before={before!r} after={after!r}"
    )


def test_relative_target_manifest_keys_stay_portable(two_projects, monkeypatch):
    """#777/#1964 portability, broken here by the CWD-derived ``root=``.

    ``project_root`` was ``Path.cwd()`` for a relative target, so the target's
    files were out-of-root and ``_to_relative_for_storage`` kept them absolute.
    A manifest with absolute keys does not survive a move or a second clone.
    """
    from graphify.watch import _rebuild_code

    proj_a, proj_b = two_projects
    monkeypatch.chdir(proj_a)

    relative_target = Path(os.path.relpath(proj_b, proj_a))
    assert not relative_target.is_absolute(), "precondition: target must be relative"
    assert _rebuild_code(relative_target, acquire_lock=False) is True

    target_manifest = proj_b / "graphify-out" / "manifest.json"
    assert target_manifest.exists(), "manifest missing from the target (#2316)"

    rows = json.loads(target_manifest.read_text(encoding="utf-8"))
    absolute_keys = [k for k in rows if Path(k).is_absolute()]
    assert not absolute_keys, (
        "manifest keys must be stored relative to the target so the manifest is "
        f"portable across checkouts (#777); got absolute keys {absolute_keys}"
    )
    assert "projb_file.py" in rows, (
        f"expected the target-relative key 'projb_file.py'; got {sorted(rows)}"
    )


def test_built_at_commit_comes_from_the_target_repo(two_projects, monkeypatch):
    """Same CWD-anchoring class as #2316, but it writes wrong data, not a wrong path.

    ``_git_head()`` ran ``git rev-parse HEAD`` with no ``cwd=``, so it read the
    invoking repo. An update of project B from project A stamped A's commit into
    B's graph.json — provenance that is confidently wrong (cf. #2081).
    """
    import subprocess

    from graphify.watch import _rebuild_code

    proj_a, proj_b = two_projects

    def _init(repo: Path, message: str) -> str:
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(["git", "init", "-q", "."], cwd=repo, check=True, env=env)
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=env)
        subprocess.run(["git", "commit", "-qm", message], cwd=repo, check=True, env=env)
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, check=True, env=env,
            capture_output=True, text=True,
        ).stdout.strip()

    head_a = _init(proj_a, "a")
    head_b = _init(proj_b, "b")
    assert head_a != head_b, "precondition: the two repos must have distinct HEADs"

    monkeypatch.chdir(proj_a)
    assert _rebuild_code(proj_b, acquire_lock=False) is True

    graph = json.loads((proj_b / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    assert graph.get("built_at_commit") == head_b, (
        "graph.json must record the commit of the repo it describes; got "
        f"{graph.get('built_at_commit')!r}, expected {head_b!r} "
        f"(the invoking repo's HEAD is {head_a!r})"
    )


def test_relative_target_manifest_is_consumable_by_detect_incremental(
    two_projects, monkeypatch
):
    """End of the chain: the point of the manifest is the next incremental run.

    A manifest anchored to the wrong root makes every file look new, which is
    the user-visible cost of #2316 even once the file is in the right place.
    """
    from graphify.detect import detect_incremental
    from graphify.watch import _rebuild_code

    proj_a, proj_b = two_projects
    monkeypatch.chdir(proj_a)

    relative_target = Path(os.path.relpath(proj_b, proj_a))
    assert _rebuild_code(relative_target, acquire_lock=False) is True

    manifest_path = proj_b / "graphify-out" / "manifest.json"
    assert manifest_path.exists(), "manifest missing from the target (#2316)"

    # Simulate the next run from a *different* CWD, as a driver script would.
    monkeypatch.chdir(proj_b.parent)
    detection = detect_incremental(proj_b, str(manifest_path), kind="ast")
    assert detection.get("incremental") is True, (
        "precondition: the manifest must have been read as a baseline at all"
    )
    new_files = [f for fl in detection.get("new_files", {}).values() for f in fl]
    assert not new_files, (
        "nothing changed on disk, so the incremental detect should queue no work; "
        f"it re-queued {new_files} — the manifest was not a usable baseline"
    )
