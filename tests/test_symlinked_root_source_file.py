"""`source_file` stays repo-relative when the scan root is reached through a symlink (#4624).

`extract()` resolves `root`, but the absolute-`source_file` relativizer called
`relative_to(root)` on the UNRESOLVED path. Under a symlinked prefix (macOS
`/var` -> `/private/var`, or any symlinked checkout) that raised, the file was
treated as out-of-root, and `source_file` collapsed to the bare basename. Every
`page.tsx` in a Next.js app then read as the same file, so pruning one deleted
`page.tsx` also pruned the re-extracted nodes of another.
"""
from __future__ import annotations

import io
import os
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from graphify.build import build_from_json, build_merge
from graphify.cluster import cluster
from graphify.export import to_json
from graphify.extract import extract

PAGE = "export default function ListPage() {\n  return helper();\n}\nfunction helper() { return 1; }\n"


def _linked_root(tmp_path: Path) -> Path:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        os.symlink(real, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable (e.g. Windows without developer mode)")
    return link


def _extract(paths: list[Path], root: Path) -> dict:
    with redirect_stdout(io.StringIO()):
        return extract(paths, cache_root=Path(tempfile.mkdtemp()), root=root, parallel=False)


def test_source_file_is_repo_relative_under_a_symlinked_root(tmp_path):
    root = _linked_root(tmp_path)
    page = root / "web/app/customers/page.tsx"
    page.parent.mkdir(parents=True)
    page.write_text(PAGE, encoding="utf-8")

    result = _extract([page], root)

    assert {n["source_file"] for n in result["nodes"]} == {"web/app/customers/page.tsx"}


def test_same_basename_files_stay_distinct_under_a_symlinked_root(tmp_path):
    root = _linked_root(tmp_path)
    a = root / "web/app/a/page.tsx"
    b = root / "web/app/b/page.tsx"
    for p in (a, b):
        p.parent.mkdir(parents=True)
        p.write_text(PAGE, encoding="utf-8")

    result = _extract([a, b], root)

    assert {n["source_file"] for n in result["nodes"]} == {"web/app/a/page.tsx", "web/app/b/page.tsx"}


def test_pruning_a_deleted_page_keeps_the_reextracted_one(tmp_path):
    """The user-visible failure: an incremental merge emptied the graph."""
    root = _linked_root(tmp_path)
    old = root / "web/app/customers-list/page.tsx"
    old.parent.mkdir(parents=True)
    old.write_text(PAGE, encoding="utf-8")
    G = build_from_json(_extract([old], root), root=str(root))
    out = root / "graphify-out"
    out.mkdir()
    with redirect_stdout(io.StringIO()):
        assert to_json(G, cluster(G), str(out / "graph.json"))

    old.unlink()
    new = root / "web/app/customers/list/page.tsx"
    new.parent.mkdir(parents=True)
    new.write_text(PAGE, encoding="utf-8")
    fresh = _extract([new], root)
    with redirect_stdout(io.StringIO()):
        merged = build_merge([fresh], graph_path=str(out / "graph.json"),
                             prune_sources=[str(old)], root=str(root))

    kept = {n: d.get("source_file") for n, d in merged.nodes(data=True)}
    assert {n["id"] for n in fresh["nodes"]} <= set(kept)
    assert set(kept.values()) == {"web/app/customers/list/page.tsx"}
