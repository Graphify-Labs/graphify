"""#2230: incremental symbol resolution must regenerate INFERRED cross-file
edges to symbols defined in an unchanged neighbor.

Cross-file resolution (`_augment_symbol_resolution_edges` and
`_resolve_cross_file_imports`) used to index only nodes extracted THIS run,
so an incremental rebuild of a single changed file could never re-bind an
edge whose target lives in an unchanged sibling: the merge correctly drops
the graph's old copy of that edge (the changed file's result replaced it),
and nothing regenerates it. Passing the unchanged corpus in via
`resolution_context_nodes` (the same mechanism #2406 added for direct/
indirect call resolution) must widen these two passes as well.
"""

from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write_corpus(root: Path) -> list[Path]:
    pkg = root / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "exc.py").write_text("class BadData(Exception):\n    pass\n")
    (pkg / "a.py").write_text(
        "from .exc import BadData\n\n\ndef load():\n    raise BadData()\n"
    )
    return [pkg / "__init__.py", pkg / "exc.py", pkg / "a.py"]


def _edge_set(graph: dict) -> set[tuple[str, str, str]]:
    return {(e["source"], e["target"], e["relation"]) for e in graph["edges"]}


def test_incremental_reextract_regenerates_cross_file_edges(tmp_path):
    root = tmp_path
    paths = _write_corpus(root)

    full = extract(paths, root=root, cache_root=root, parallel=False)
    full_edges = _edge_set(full)

    # Every edge the full scan sourced from a.py must reappear when a.py alone
    # is re-extracted incrementally, with exc.py supplied only as read-only
    # resolution context (an unchanged neighbor, never re-parsed).
    full_a_edges = {e for e in full_edges if e[0].startswith("pkg_a")}
    assert full_a_edges, "sanity: full scan should produce edges sourced by a.py"
    assert any(e[2] == "uses" for e in full_a_edges), (
        "sanity: full scan should produce a cross-file INFERRED 'uses' edge"
    )

    context_nodes = [
        n for n in full["nodes"]
        if str(n.get("source_file", "")).endswith(("exc.py", "__init__.py"))
    ]

    incremental = extract(
        [root / "pkg" / "a.py"],
        root=root,
        cache_root=root,
        parallel=False,
        resolution_context_nodes=context_nodes,
    )
    incremental_a_edges = {
        e for e in _edge_set(incremental) if e[0].startswith("pkg_a")
    }

    assert incremental_a_edges == full_a_edges, (
        f"incremental re-extraction lost cross-file edges: "
        f"{full_a_edges - incremental_a_edges}"
    )
