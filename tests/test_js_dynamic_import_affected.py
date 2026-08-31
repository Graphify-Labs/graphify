"""`affected` must traverse a dynamic `import('…')` written inside a function — #2584.

The edge was already emitted (#2575), so an edge-existence assertion passes while the
answer users actually read is short. The reason is a granularity mismatch: a static import
emits ``file -> target``, but ``_dynamic_import_js`` emitted ``caller_nid -> target``, and
``caller_nid`` is the file node ONLY at module level. Written inside a function it is that
function's node, so the graph held ``load() --imports_from--> target`` with no file-level
edge, and the reverse walk stopped at ``load()`` — the one edge pointing at it is
``contains``, which is deliberately not in DEFAULT_AFFECTED_RELATIONS.

Measured on a ~700-file TS repo: recall 0.80 at depth 3, precision 1.00, and raising the
depth did not help. It stayed hidden because the common case works — if the next importer
imports that exact symbol by name, there IS an edge into ``load()``. So the tests below
pin the cases where nothing points at the enclosing symbol: a namespace import and a
side-effect import. Those are the ones that were silent.
"""
from __future__ import annotations

from pathlib import Path

import networkx as nx

from graphify.affected import affected_nodes
from graphify.extract import _file_node_id, extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


TARGET = "export const value = 1\n"

# The dynamic import lives INSIDE a function — the case that regressed.
DYN_IN_FUNCTION = (
    "export async function load() {\n"
    "    const m = await import('./target')\n"
    "    return m.value\n"
    "}\n"
    "export const other = 2\n"
)

TOP = "import { run } from './mid'\nexport const go = () => run()\n"


def _build(tmp_path: Path, mid_src: str, dyn_src: str = DYN_IN_FUNCTION):
    files = [
        _write(tmp_path / "src/target.ts", TARGET),
        _write(tmp_path / "src/dyn.ts", dyn_src),
        _write(tmp_path / "src/mid.ts", mid_src),
        _write(tmp_path / "src/top.ts", TOP),
    ]
    result = extract(files, cache_root=tmp_path, root=tmp_path)
    graph = nx.DiGraph()
    for n in result["nodes"]:
        graph.add_node(n["id"], **n)
    for e in result["edges"]:
        graph.add_edge(e["source"], e["target"], **e)
    return result, graph


def _fid(rel: str) -> str:
    return _file_node_id(Path(rel))


def _reaches(graph: nx.DiGraph, seed: str, wanted: str, depth: int = 3) -> bool:
    hits = affected_nodes(graph, _fid(seed), depth=depth)
    return _fid(wanted) in {h.node_id for h in hits}


def _file_edges(result: dict, source: str, target: str) -> list[dict]:
    return [
        e for e in result["edges"]
        if e["source"] == _fid(source) and e["target"] == _fid(target)
    ]


def test_dynamic_import_in_function_emits_a_file_level_edge(tmp_path: Path):
    """The file owning the `import()` depends on the target, whoever wrote the call."""
    result, _ = _build(tmp_path, "import './dyn'\nexport const run = () => 1\n")

    edges = _file_edges(result, "src/dyn.ts", "src/target.ts")
    assert edges, "no file-level edge for a dynamic import written inside a function"
    # `dynamic_import`, not `imports_from`: it keeps the deferred nature legible, it is
    # already in DEFAULT_AFFECTED_RELATIONS, and find_import_cycles reads only
    # `imports_from`/`re_exports` — so the phantom file cycle of #1241 cannot come back
    # through this edge the way a second `imports_from` might.
    assert all(e["relation"] == "dynamic_import" for e in edges)


def test_affected_reaches_through_a_side_effect_importer(tmp_path: Path):
    """`import './dyn'` binds no symbol, so nothing points at the enclosing function."""
    _, graph = _build(tmp_path, "import './dyn'\nexport const run = () => 1\n")

    assert _reaches(graph, "src/target.ts", "src/dyn.ts", depth=1)
    assert _reaches(graph, "src/target.ts", "src/top.ts", depth=3)


def test_affected_reaches_through_a_namespace_importer(tmp_path: Path):
    """`import * as ns` binds the module, not the function that defers the load."""
    _, graph = _build(tmp_path, "import * as ns from './dyn'\nexport const run = () => ns.load()\n")

    assert _reaches(graph, "src/target.ts", "src/top.ts", depth=3)


def test_affected_reaches_when_importer_names_a_different_symbol(tmp_path: Path):
    """`other` is a sibling export; the edge into `load()` that used to rescue this is absent."""
    _, graph = _build(tmp_path, "import { other } from './dyn'\nexport const run = () => other\n")

    assert _reaches(graph, "src/target.ts", "src/top.ts", depth=3)


def test_call_site_precision_is_preserved(tmp_path: Path):
    """The symbol-level edge must survive: `explain` still has to name the deferring function."""
    result, _ = _build(tmp_path, "import { load } from './dyn'\nexport const run = () => load()\n")

    tgt = _fid("src/target.ts")
    symbol_edges = [
        e for e in result["edges"]
        if e["target"] == tgt and e["source"] != _fid("src/dyn.ts")
        and e.get("deferred") is True
    ]
    assert symbol_edges, "the symbol-level dynamic-import edge was replaced instead of added"
    assert symbol_edges[0]["relation"] == "imports_from"


def test_module_level_dynamic_import_emits_no_duplicate(tmp_path: Path):
    """At module level `caller_nid` IS the file node — emitting again would double-count."""
    result, _ = _build(
        tmp_path,
        "import './dyn'\nexport const run = () => 1\n",
        dyn_src="export const p = import('./target')\n",
    )

    assert len(_file_edges(result, "src/dyn.ts", "src/target.ts")) == 1


def test_one_file_deferring_the_same_module_twice_emits_one_file_edge(tmp_path: Path):
    """Two functions, one dependency. The file-level edge dedupes on its own key."""
    result, _ = _build(
        tmp_path,
        "import './dyn'\nexport const run = () => 1\n",
        dyn_src=(
            "export async function a() {\n"
            "    return (await import('./target')).value\n"
            "}\n"
            "export async function b() {\n"
            "    return (await import('./target')).value\n"
            "}\n"
        ),
    )

    assert len(_file_edges(result, "src/dyn.ts", "src/target.ts")) == 1
