"""The incremental path of ``_rebuild_code`` (#4740).

``graphify update`` used to re-extract the whole corpus on every run. These tests
cover the change set it derives from the manifest instead, and the ways that
derivation has to decline and fall back to the full path.

The asymmetry under test: a wrong "changed" costs time, a wrong "unchanged" ships
a stale graph. Every case here either proves work is skipped or proves it is NOT
skipped when the baseline is unknown.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

import graphify.extract as extract_mod
from graphify.watch import _rebuild_code

MANIFEST = "manifest.json"

# Strip any working LLM backend so a developer's exported key cannot change what
# these runs do. `update` is AST-only and needs none of them.
_LLM_ENV_KEYS = (
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY", "OLLAMA_BASE_URL",
    "AWS_PROFILE", "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_ACCESS_KEY_ID",
)


def _cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in _LLM_ENV_KEYS}
    return subprocess.run(
        [sys.executable, "-m", "graphify"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )


def _corpus(root: Path) -> Path:
    """Four code files, one of which imports across files."""
    (root / "src").mkdir(parents=True, exist_ok=True)
    for name in ("a", "b", "c"):
        (root / "src" / f"{name}.py").write_text(f"def f{name}():\n    return 1\n")
    (root / "src" / "uses.py").write_text(
        "from src.a import fa\n\ndef use():\n    return fa()\n"
    )
    return root


@pytest.fixture()
def built(tmp_path: Path) -> Path:
    root = _corpus(tmp_path / "corpus")
    assert _rebuild_code(root, acquire_lock=False) is True
    assert (root / "graphify-out" / MANIFEST).exists()
    return root


def _spy_extract(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Record the basename of every file each extract() call is handed."""
    calls: list[list[str]] = []
    real = extract_mod.extract

    def spy(targets, **kwargs):
        calls.append(sorted(Path(p).name for p in targets))
        return real(targets, **kwargs)

    monkeypatch.setattr(extract_mod, "extract", spy)
    return calls


def _outputs(root: Path) -> dict[str, tuple[bytes, int]]:
    out = root / "graphify-out"
    return {
        p.name: (p.read_bytes(), p.stat().st_mtime_ns)
        for p in sorted(out.iterdir())
        if p.is_file()
    }


def _sources(graph: Path) -> set[str]:
    payload = json.loads(graph.read_text(encoding="utf-8"))
    return {
        Path(node["source_file"]).name
        for node in payload["nodes"]
        if node.get("source_file")
    }


def test_unchanged_copied_checkout_re_extracts_nothing(
    built: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The reporter's workflow: the checkout is copied, graphify-out and all. The
    # manifest travels with it with relative keys, so the copy is a usable
    # baseline and nothing needs re-extracting.
    copy = tmp_path / "copy"
    shutil.copytree(built, copy)

    before = _outputs(copy)
    calls = _spy_extract(monkeypatch)
    assert _rebuild_code(copy, incremental=True, acquire_lock=False) is True

    assert calls == [], f"nothing changed, but extract() saw {calls}"
    assert _outputs(copy) == before


def test_only_changed_files_are_re_extracted(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _spy_extract(monkeypatch)
    (built / "src" / "a.py").write_text("def fa():\n    return 11\n")
    (built / "src" / "uses.py").write_text(
        "from src.a import fa\n\ndef use():\n    return fa() + 1\n"
    )
    # Force a different mtime from the manifest's, which is all the comparison
    # needs once the content hash agrees.
    time.sleep(0.01)

    assert _rebuild_code(built, incremental=True, acquire_lock=False) is True

    assert len(calls) == 1
    assert calls[0] == ["a.py", "uses.py"]


def test_mtime_bump_with_identical_content_is_not_re_extracted(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The manifest is content-addressed. Touching a file must not cost a rebuild,
    # or every `git checkout` of an unchanged branch would.
    (built / "src" / "b.py").touch()
    time.sleep(0.01)
    (built / "src" / "b.py").touch()

    calls = _spy_extract(monkeypatch)
    assert _rebuild_code(built, incremental=True, acquire_lock=False) is True
    assert calls == []


def test_added_file_is_re_extracted_and_deleted_file_drops_its_nodes(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = built / "graphify-out" / "graph.json"
    assert "c.py" in _sources(graph)

    (built / "src" / "c.py").unlink()
    (built / "src" / "new.py").write_text("def brand_new():\n    return 5\n")
    time.sleep(0.01)

    calls = _spy_extract(monkeypatch)
    assert _rebuild_code(built, incremental=True, acquire_lock=False) is True

    # The added file is work; the deleted file is not extracted but must reach
    # the eviction pass, or its nodes survive and the shrink guard blames a
    # source nothing touched.
    assert calls == [["new.py"]]
    assert "c.py" not in _sources(graph)
    assert "new.py" in _sources(graph)


def test_default_is_the_full_path(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The watcher and the post-checkout hook call this with incremental unset, and
    # their behaviour must not change: the whole corpus is re-extracted, unlike
    # the subset that test_only_changed_files_are_re_extracted pins for
    # incremental=True.
    #
    # One change first, so the assertion holds whether or not the #4740 no-change
    # gate is present: a correct gate can never skip a tree that changed, so the
    # run reaches the pipeline either way.
    (built / "src" / "a.py").write_text("def fa():\n    return 99\n")
    time.sleep(0.01)

    calls = _spy_extract(monkeypatch)
    assert _rebuild_code(built, acquire_lock=False) is True
    assert calls == [["a.py", "b.py", "c.py", "uses.py"]]


def test_force_keeps_the_full_path(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _spy_extract(monkeypatch)
    assert _rebuild_code(built, incremental=True, force=True, acquire_lock=False) is True
    assert calls == [["a.py", "b.py", "c.py", "uses.py"]]


def test_explicit_changed_paths_win_over_incremental(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A caller that already knows its change set (a hook) must keep it.
    calls = _spy_extract(monkeypatch)
    ok = _rebuild_code(
        built,
        changed_paths=[built / "src" / "a.py"],
        incremental=True,
        acquire_lock=False,
    )
    assert ok is True
    assert calls == [["a.py"]]


def test_missing_manifest_keeps_the_full_path(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No baseline means "unknown", and unknown must mean "do the work" — an
    # empty change set here would skip the rebuild entirely.
    (built / "graphify-out" / MANIFEST).unlink()

    calls = _spy_extract(monkeypatch)
    assert _rebuild_code(built, incremental=True, acquire_lock=False) is True
    assert calls == [["a.py", "b.py", "c.py", "uses.py"]]


def test_unreadable_manifest_keeps_the_full_path(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (built / "graphify-out" / MANIFEST).write_text("{not json", encoding="utf-8")

    calls = _spy_extract(monkeypatch)
    assert _rebuild_code(built, incremental=True, acquire_lock=False) is True
    assert calls == [["a.py", "b.py", "c.py", "uses.py"]]


def test_manifest_anchored_elsewhere_keeps_the_full_path(
    built: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Rows whose paths do not name this corpus (a manifest copied from another
    # tree, or a stale absolute-keyed one) cannot classify anything here. Every
    # file then has "no row you can verify", which counts as changed.
    manifest = built / "graphify-out" / MANIFEST
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    other = tmp_path / "elsewhere"
    manifest.write_text(
        json.dumps({str(other / Path(k).name): v for k, v in payload.items()}),
        encoding="utf-8",
    )

    calls = _spy_extract(monkeypatch)
    assert _rebuild_code(built, incremental=True, acquire_lock=False) is True
    assert calls == [["a.py", "b.py", "c.py", "uses.py"]]


def test_incremental_second_run_matches_a_full_rebuild(
    built: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The point of the change set: after it, the graph is the one a full rebuild
    # of the same tree would have produced.
    def edit(root: Path) -> None:
        (root / "src" / "a.py").write_text("def renamed_fa():\n    return 11\n")
        (root / "src" / "uses.py").write_text(
            "from src.a import renamed_fa\n\ndef use():\n    return renamed_fa()\n"
        )
        (root / "src" / "c.py").unlink()
        (root / "src" / "new.py").write_text("def brand_new():\n    return 5\n")

    other = _corpus(tmp_path / "other")
    assert _rebuild_code(other, acquire_lock=False) is True

    # `built` was already populated by the fixture; both trees get the same edit.
    edit(built)
    edit(other)
    assert _rebuild_code(built, incremental=True, acquire_lock=False) is True
    assert _rebuild_code(other, acquire_lock=False) is True

    assert _graph_shape(built) == _graph_shape(other)


def test_incremental_survives_the_lock_path(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `graphify update` takes the per-repo lock (blocking), so the change set has
    # to survive the queued-request drain. The drain reads changed_paths=None as
    # "the caller wants the full corpus", which is what an incremental request
    # also looks like — and that reading quietly turned every locked incremental
    # run into a full rebuild.
    calls = _spy_extract(monkeypatch)
    (built / "src" / "a.py").write_text("def renamed_fa():\n    return 11\n")
    time.sleep(0.01)

    assert _rebuild_code(built, incremental=True, block_on_lock=True) is True
    assert calls == [["a.py"]]


def test_incremental_does_not_queue_a_full_rebuild(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A non-blocking incremental request must not leave a .pending_full marker:
    # the next drain would read it as "re-extract everything", turning someone
    # else's cheap update into a full rebuild.
    (built / "src" / "a.py").write_text("def renamed_fa():\n    return 11\n")
    time.sleep(0.01)

    calls = _spy_extract(monkeypatch)
    assert _rebuild_code(built, incremental=True) is True
    assert calls == [["a.py"]]
    assert not (built / "graphify-out" / ".pending_full").exists()


def _graph_shape(root: Path):
    payload = json.loads((root / "graphify-out" / "graph.json").read_text())
    nodes = sorted(
        (n.get("id"), n.get("label"), n.get("source_file")) for n in payload["nodes"]
    )
    links = sorted(
        (e.get("source"), e.get("target"), e.get("relation"))
        for e in payload.get("links", payload.get("edges", []))
    )
    return nodes, links


def _cross_file_calls(root: Path) -> set[str]:
    """``src:label -> dst:label`` for every calls edge that spans two files."""
    payload = json.loads((root / "graphify-out" / "graph.json").read_text())
    labels = {
        n["id"]: (Path(n.get("source_file") or "?").name, n.get("label"))
        for n in payload["nodes"]
    }
    edges: set[str] = set()
    for edge in payload.get("links", payload.get("edges", [])):
        src = labels.get(edge.get("source"))
        dst = labels.get(edge.get("target"))
        if edge.get("relation") == "calls" and src and dst and src[0] != dst[0]:
            edges.add(f"{src[0]}:{src[1]} -> {dst[0]}:{dst[1]}")
    return edges


def _add_caller_of_fa(root: Path) -> None:
    """Add a second caller of ``a.py:fa()`` to ``uses.py`` and nothing else."""
    (root / "src" / "uses.py").write_text(
        "from src.a import fa\n\ndef use():\n    return fa()\n\ndef added():\n    return fa()\n"
    )


def test_cross_file_call_edge_survives_an_incremental_update(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Only uses.py changes, and its new caller lives there — but the callee is in
    # an untouched file, so the edge can only be rebuilt from the resolution
    # context (the #2406/#3763 failure mode).
    assert "uses.py:use() -> a.py:fa()" in _cross_file_calls(built)

    _add_caller_of_fa(built)
    assert _rebuild_code(built, incremental=True, acquire_lock=False) is True

    edges = _cross_file_calls(built)
    assert "uses.py:added() -> a.py:fa()" in edges
    assert "uses.py:use() -> a.py:fa()" in edges


def test_cross_file_call_edge_survives_a_copied_checkout(
    built: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Same as above on a copied checkout, where graphify-out/.graphify_root still
    # names the original tree. Stored source paths then resolve against the old
    # root, which used to make the whole resolve context look corpus-absent.
    copy = tmp_path / "copy"
    shutil.copytree(built, copy)
    assert "uses.py:use() -> a.py:fa()" in _cross_file_calls(copy)

    _add_caller_of_fa(copy)
    assert _rebuild_code(copy, incremental=True, acquire_lock=False) is True

    assert "uses.py:added() -> a.py:fa()" in _cross_file_calls(copy)


def test_cli_update_re_extracts_only_changed_files(tmp_path: Path) -> None:
    # End to end through the command the user runs. The first run has no
    # baseline, so it must be full; the second must not be.
    root = _corpus(tmp_path / "tree")
    first = _cli(["update", "."], root)
    assert first.returncode == 0, first.stderr
    assert "Incremental:" not in first.stdout

    (root / "src" / "a.py").write_text("def renamed_fa():\n    return 11\n")
    second = _cli(["update", "."], root)
    assert second.returncode == 0, second.stderr
    assert "Incremental: re-extracting 1 of 4 scanned files" in second.stdout

    # And the result is the graph a full rebuild of the same tree produces.
    other = _corpus(tmp_path / "other")
    (other / "src" / "a.py").write_text("def renamed_fa():\n    return 11\n")
    full = _cli(["update", "."], other)
    assert full.returncode == 0, full.stderr

    assert _graph_shape(root) == _graph_shape(other)


def test_cli_update_force_keeps_the_full_path(tmp_path: Path) -> None:
    # The escape hatch: `--force` must not be silently downgraded to a change
    # set, or a user reaching for it cannot shake a graph they distrust.
    root = _corpus(tmp_path / "tree")
    assert _cli(["update", "."], root).returncode == 0

    forced = _cli(["update", ".", "--force"], root)
    assert forced.returncode == 0, forced.stderr
    assert "Incremental:" not in forced.stdout
