"""Two files importing each other are an Import Cycle in the default build (#4839).

The undirected build keeps one edge per file pair and drops the reverse-direction
duplicate (#1061). For `imports_from`/`re_exports` that dropped leg is the other
half of the cycle, so it is kept as a `reverse_import` stamp on the surviving
edge and `find_import_cycles` reads it back.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from graphify.analyze import find_import_cycles
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return extract([tmp_path / n for n in files], cache_root=Path(tempfile.mkdtemp()),
                   root=tmp_path, parallel=False)


def _build(tmp_path, files, directed=False):
    r = _extract(tmp_path, files)
    return build_from_json({"nodes": r["nodes"], "edges": r["edges"], "hyperedges": []},
                           root=str(tmp_path), directed=directed)


def _names(cycles):
    return sorted(sorted(Path(f).name for f in c["cycle"]) for c in cycles)


_TS_CYCLE = {
    "src/a.ts": "import { B } from './b';\nexport class A { b?: B; }\n",
    "src/b.ts": "import { A } from './a';\nexport class B { a?: A; }\n",
}
_PY_CYCLE = {
    "a.py": "from b import B\n\nclass A:\n    b: B = None\n",
    "b.py": "from a import A\n\nclass B:\n    a: A = None\n",
}


@pytest.mark.parametrize("files, expected", [
    (_TS_CYCLE, [["a.ts", "b.ts"]]),
    (_PY_CYCLE, [["a.py", "b.py"]]),
], ids=["ts", "python"])
def test_two_file_cycle_is_reported_in_the_undirected_build(tmp_path, files, expected):
    G = _build(tmp_path, files)
    imports = [d for *_e, d in G.edges(data=True) if d.get("relation") == "imports_from"]
    assert len(imports) == 1  # still one stored edge per pair (#1061)
    assert imports[0].get("reverse_import") is True
    assert _names(find_import_cycles(G)) == expected


def test_a_one_way_import_is_not_a_cycle(tmp_path):
    G = _build(tmp_path, {
        "a.py": "from b import B\n\nclass A:\n    b: B = None\n",
        "b.py": "class B:\n    pass\n",
    })
    assert not any(d.get("reverse_import") for *_e, d in G.edges(data=True))
    assert find_import_cycles(G) == []


def test_longer_cycles_are_still_reported_beside_a_two_file_one(tmp_path):
    G = _build(tmp_path, {
        "a.py": "from b import B\nclass A: pass\n",
        "b.py": "from a import A\nfrom c import C\nclass B: pass\n",
        "c.py": "from a import A\nclass C: pass\n",
    })
    assert _names(find_import_cycles(G)) == [["a.py", "b.py"], ["a.py", "b.py", "c.py"]]


@pytest.mark.parametrize("files", [
    {"a.ts": "import { B } from './b';\nexport type AT = number;\nexport const a = 1;\n",
     "b.ts": "import type { AT } from './a';\nexport class B {}\n"},
    {"a.py": "from b import B\n\nclass A:\n    b: B = None\n",
     "b.py": ("from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from a import A\n\n"
              "class B:\n    a: 'A' = None\n")},
], ids=["ts-import-type", "python-type-checking"])
def test_a_type_only_reverse_import_closes_no_cycle(tmp_path, files):
    G = _build(tmp_path, files)
    assert not any(d.get("reverse_import") for *_e, d in G.edges(data=True))
    assert find_import_cycles(G) == []


def _edge(src, tgt, rel="imports_from", **extra):
    return {"source": src, "target": tgt, "relation": rel, "confidence": "EXTRACTED",
            "source_file": f"{src}.py", "source_location": "L1", **extra}


def _graph(edges, directed=False):
    nodes = [{"id": n, "label": f"{n}.py", "source_file": f"{n}.py", "file_type": "code"}
             for n in ("a", "b")]
    return build_from_json({"nodes": nodes, "edges": edges, "hyperedges": []}, directed=directed)


@pytest.mark.parametrize("reverse", [
    _edge("b", "a", "calls"),
    _edge("b", "a", "imports"),
    _edge("b", "a", deferred=True),
    _edge("b", "a", type_only=True),
], ids=["other-relation", "symbol-imports", "deferred", "type-only"])
def test_only_a_runtime_reverse_import_stamps_the_kept_edge(reverse):
    G = _graph([_edge("a", "b"), reverse])
    assert not any(d.get("reverse_import") for *_e, d in G.edges(data=True))
    assert find_import_cycles(G) == []


def test_the_directed_build_is_unchanged():
    G = _graph([_edge("a", "b"), _edge("b", "a")], directed=True)
    assert G.number_of_edges() == 2
    assert not any("reverse_import" in d for *_e, d in G.edges(data=True))
    assert _names(find_import_cycles(G)) == [["a.py", "b.py"]]


def test_the_cycle_survives_a_graph_json_round_trip(tmp_path):
    G = _build(tmp_path, _TS_CYCLE)
    graph_path = tmp_path / "graph.json"
    assert to_json(G, {}, str(graph_path), force=True)
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    G2 = build_from_json({"nodes": data["nodes"], "edges": data["links"], "hyperedges": []},
                         directed=bool(data.get("directed")))
    assert _names(find_import_cycles(G2)) == [["a.ts", "b.ts"]]


# Incremental (hook) rebuilds ------------------------------------------------

def _rebuild_cycles(root, changed=None):
    from graphify.watch import _rebuild_code

    assert _rebuild_code(root, changed_paths=changed, acquire_lock=False, force=True)
    data = json.loads((root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    G = build_from_json({"nodes": data["nodes"], "edges": data["links"], "hyperedges": []},
                        directed=bool(data.get("directed")))
    return _names(find_import_cycles(G))


def test_an_incremental_rebuild_drops_the_stamp_with_the_reverse_import(tmp_path):
    """The stamp is b.py's import, stored on a.py's edge: when b.py stops
    importing a.py, re-extracting b.py alone must not leave a stale cycle."""
    for name, body in _PY_CYCLE.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    assert _rebuild_cycles(tmp_path) == [["a.py", "b.py"]]
    (tmp_path / "b.py").write_text("class B:\n    pass\n", encoding="utf-8")
    assert _rebuild_cycles(tmp_path, [tmp_path / "b.py"]) == []


def test_an_incremental_rebuild_of_the_kept_edges_file_keeps_the_cycle(tmp_path):
    for name, body in _PY_CYCLE.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    assert _rebuild_cycles(tmp_path) == [["a.py", "b.py"]]
    (tmp_path / "a.py").write_text("# edited\n" + _PY_CYCLE["a.py"], encoding="utf-8")
    assert _rebuild_cycles(tmp_path, [tmp_path / "a.py"]) == [["a.py", "b.py"]]
    (tmp_path / "a.py").write_text("class A:\n    pass\n", encoding="utf-8")
    assert _rebuild_cycles(tmp_path, [tmp_path / "a.py"]) == []
