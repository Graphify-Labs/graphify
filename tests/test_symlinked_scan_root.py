"""Reaching the scan root through a symlink must not change the graph.

macOS `/tmp` is a symlink to `/private/tmp`, and symlinked workspace dirs, symlinked
homes and bind/overlay mounts in CI are all common. Extracting the same files through
the symlink and through the real path used to produce different graphs: the same node
count, but fewer edges — the `calls` edges for constructor calls on classes imported
package-root-relative (src-layout, `from app.config import Settings` where the package
lives at `svc/app/`) were dropped, leaving only a generic `uses` edge.

Node IDs are clean and repo-relative in both runs, so the usual "absolute path leaked
into the IDs" symptom is absent — the IDs look right while edges are silently missing,
which reads downstream as genuine dead code rather than as a bug.
"""
from __future__ import annotations

import os
import shutil

import pytest

from pathlib import Path

from graphify.extract import collect_files, extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _corpus(root: Path) -> None:
    """A src-layout service: package root is `svc/`, imports are written from it."""
    _write(root / "svc/app/__init__.py", "")
    _write(root / "svc/app/config.py", "class Settings:\n    port = 8000\n")
    _write(root / "svc/app/main.py",
           "def create_app(settings):\n    return {'settings': settings}\n")
    _write(root / "svc/app/consumer.py",
           "from app.config import Settings\n\n\n"
           "def build():\n    return Settings()\n")
    _write(root / "svc/tests/test_api.py",
           "from app.config import Settings\n"
           "from app.main import create_app\n\n\n"
           "def make():\n    return create_app(settings=Settings())\n")


def _extract_via(root: Path) -> dict:
    # The two spellings name ONE physical directory, so they also share one
    # graphify-out/ cache. Clear it between runs: otherwise the second extraction
    # replays entries the first one keyed under the other spelling, and the test
    # measures cache reuse instead of resolution.
    shutil.rmtree(root / "graphify-out", ignore_errors=True)
    files = sorted(f for f in collect_files(root) if f.suffix == ".py")
    return extract(files, cache_root=root, parallel=False)


def _summary(result: dict) -> tuple[int, set[tuple[str, str, str]]]:
    edges = {(str(e["source"]), str(e["target"]), e["relation"]) for e in result["edges"]}
    return len(result["nodes"]), edges


@pytest.fixture()
def linked_root(tmp_path: Path) -> tuple[Path, Path]:
    """(real_root, symlinked_root) pointing at one identical corpus."""
    real = tmp_path / "real"
    _corpus(real)
    link = tmp_path / "link"
    try:
        os.symlink(real, link, target_is_directory=True)
    except (OSError, NotImplementedError):  # Windows without developer mode
        pytest.skip("symlink creation not permitted on this platform")
    return real, link


def test_symlinked_scan_root_yields_the_same_graph(linked_root) -> None:
    real, link = linked_root
    real_nodes, real_edges = _summary(_extract_via(real))
    link_nodes, link_edges = _summary(_extract_via(link))

    assert link_nodes == real_nodes, "node counts already differ"
    missing = {(s.split("svc_")[-1], t.split("svc_")[-1], r) for s, t, r in real_edges - link_edges}
    assert not missing, f"edges lost when the scan root is a symlink: {sorted(missing)}"
    assert link_edges == real_edges


def test_symlinked_scan_root_keeps_constructor_calls(linked_root) -> None:
    # The concrete symptom: `Settings()` in a src-layout importer.
    _, link = linked_root
    edges = _summary(_extract_via(link))[1]
    for caller in ("svc_app_consumer_build", "svc_tests_test_api_make"):
        rels = {r for s, t, r in edges if s == caller and t == "svc_app_config_settings"}
        assert "calls" in rels, f"{caller} lost its `calls` edge to Settings (got {rels or 'nothing'})"


def test_symlinked_scan_root_keeps_repo_relative_ids(linked_root) -> None:
    # Guard the fix's shape: resolving the root must not push absolute paths into IDs.
    _, link = linked_root
    ids = {n["id"] for n in _extract_via(link)["nodes"]}
    assert "svc_app_config_settings" in ids, sorted(ids)
    assert not any(i.startswith(("private_", "tmp_", "var_", "users_")) for i in ids), sorted(ids)
