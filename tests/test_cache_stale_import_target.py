"""An AST cache hit must not replay an import resolved to a file that is gone.

A cache entry is keyed by its own file's content, so an unchanged importer kept
its import edge to a module after that module was renamed or deleted. The edge
target was the id minted from the old file's absolute path, which extract() maps
to a portable id only for targets that exist, so the checkout path reached
graph.json and a warm update differed from a cold build of the same tree.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from graphify.cache import load_cached, save_cached


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _import_result(importer: Path, target: Path) -> dict:
    return {
        "nodes": [{"id": "pkg_user", "source_file": str(importer)}],
        "edges": [{
            "source": "pkg_user", "target": "x", "relation": "imports_from",
            "source_file": str(importer), "target_file": str(target),
        }],
    }


def test_hit_is_a_miss_once_a_recorded_import_target_is_gone(tmp_path: Path):
    importer = _write(tmp_path / "pkg" / "user.py", "from pkg.slice import cut\n")
    target = _write(tmp_path / "pkg" / "slice.py", "def cut(p):\n    return p\n")
    save_cached(importer, _import_result(importer, target), root=tmp_path, kind="ast")

    hit = load_cached(importer, root=tmp_path, kind="ast")
    assert hit is not None
    assert "_cached_target_files" not in hit, "bookkeeping must not reach extraction results"

    target.rename(tmp_path / "pkg" / "slicing.py")
    assert load_cached(importer, root=tmp_path, kind="ast") is None

    (tmp_path / "pkg" / "slicing.py").rename(target)
    assert load_cached(importer, root=tmp_path, kind="ast") is not None


def test_target_missing_when_written_does_not_invalidate(tmp_path: Path):
    """Extractors may stamp a speculative target that does not exist yet; such an
    entry stays a hit, as before."""
    importer = _write(tmp_path / "pkg" / "user.py", "from .later import f\n")
    save_cached(importer, _import_result(importer, tmp_path / "pkg" / "later.py"), root=tmp_path, kind="ast")
    assert load_cached(importer, root=tmp_path, kind="ast") is not None


def test_recorded_targets_are_portable_across_roots(tmp_path: Path):
    a = tmp_path / "a"
    importer = _write(a / "pkg" / "user.py", "from pkg.slice import cut\n")
    target = _write(a / "pkg" / "slice.py", "def cut(p):\n    return p\n")
    save_cached(importer, _import_result(importer, target), root=a, kind="ast", cache_root=tmp_path)

    b = tmp_path / "b"
    shutil.copytree(a, b)
    assert load_cached(b / "pkg" / "user.py", root=b, kind="ast", cache_root=tmp_path) is not None
    (b / "pkg" / "slice.py").unlink()
    assert load_cached(b / "pkg" / "user.py", root=b, kind="ast", cache_root=tmp_path) is None


@pytest.mark.parametrize("change", ["rename", "delete"])
def test_warm_update_after_removing_an_imported_module_matches_a_cold_build(tmp_path: Path, change: str):
    from graphify.watch import _rebuild_code

    def corpus(root: Path) -> Path:
        _write(root / "pkg" / "__init__.py", "")
        _write(root / "pkg" / "slice.py", "def cut(p):\n    return p\n")
        _write(root / "pkg" / "user.py", "from pkg.slice import cut\nimport pkg.slice\n\n\ndef go(p):\n    return cut(p)\n")
        return root

    def remove(root: Path) -> None:
        if change == "rename":
            (root / "pkg" / "slice.py").rename(root / "pkg" / "slicing.py")
        else:
            (root / "pkg" / "slice.py").unlink()

    def graph(root: Path) -> tuple[set[str], set[tuple[str, str, str]]]:
        data = json.loads((root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
        return (
            {n["id"] for n in data["nodes"]},
            {(e["source"], e["target"], e["relation"]) for e in data["links"]},
        )

    warm = corpus(tmp_path / "checkout_warm" / "proj")
    assert _rebuild_code(warm, no_cluster=True, acquire_lock=False) is True
    remove(warm)
    assert _rebuild_code(warm, no_cluster=True, force=True, acquire_lock=False) is True

    cold = corpus(tmp_path / "checkout_cold" / "proj")
    remove(cold)
    assert _rebuild_code(cold, no_cluster=True, acquire_lock=False) is True

    warm_ids, warm_edges = graph(warm)
    assert not [i for i in warm_ids if "checkout_warm" in i], "a node id embeds the checkout path"
    assert (warm_ids, warm_edges) == graph(cold)
