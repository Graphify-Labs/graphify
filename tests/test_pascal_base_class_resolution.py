"""Regression tests for cross-file Pascal/Delphi base-class resolution.

``_pascal_resolve_class`` maps a base class name to a file by naming
convention alone -- ``TFooBar`` is assumed to live in ``FooBar.pas``. A class
declared in a unit named anything else produces one private stub node per
inheriting file, so an inheritance hierarchy that is one tree in the compiler
arrives as disconnected two-node fragments, and ``resolve_pascal_inherited_calls``
-- which walks that chain -- resolves almost nothing.

``graphify.pascal_class_resolution`` retargets those edges onto the node where
the class is actually declared. See its module docstring for the rationale.

The fixtures mirror the shape that breaks the convention: ``TXForm`` is
declared in ``XFormP.pas``, not ``XForm.pas``. Static fixtures rather than
tmp_path, for the reason given in tests/test_pascal_resolution.py.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract, extract_pascal

FIXTURES = Path(__file__).parent / "fixtures" / "pascal_base_class"
BASE = FIXTURES / "XFormP.pas"
DERIVED = FIXTURES / "FillAkord.pas"


def _labels(nodes: list[dict]) -> dict[str, str]:
    return {n["id"]: str(n.get("label", "")) for n in nodes}


def _nodes_by_label(graph: dict, label: str) -> list[dict]:
    return [n for n in graph["nodes"] if str(n.get("label", "")) == label]


def _edge(graph: dict, relation: str, src_label: str, tgt_label: str):
    labels = _labels(graph["nodes"])
    for edge in graph["edges"]:
        if edge.get("relation") != relation:
            continue
        if (labels.get(edge.get("source")) == src_label
                and labels.get(edge.get("target")) == tgt_label):
            return edge
    return None


def test_single_file_extraction_creates_a_local_stub():
    """Sanity check for the gap this resolver closes: extracting the derived
    unit alone cannot see XFormP.pas, so the base class must arrive as a stub
    in the derived file rather than as a wrong guess."""
    result = extract_pascal(DERIVED)
    stubs = [n for n in result["nodes"] if str(n.get("label")) == "TXForm"]
    assert stubs, "base class should still be represented"
    assert all(str(n["source_file"]).endswith("FillAkord.pas") for n in stubs)


def test_inherits_points_at_the_declaring_unit(tmp_path):
    graph = extract([BASE, DERIVED], cache_root=tmp_path, parallel=False)
    edge = _edge(graph, "inherits", "TfrmFillAkord", "TXForm")
    assert edge is not None
    target = next(n for n in graph["nodes"] if n["id"] == edge["target"])
    assert str(target["source_file"]).endswith("XFormP.pas")


def test_the_base_class_is_one_node_not_one_per_file(tmp_path):
    """The fragmentation this fixes: before, every inheriting file carried its
    own TXForm, so the hierarchy could not be traversed."""
    graph = extract([BASE, DERIVED], cache_root=tmp_path, parallel=False)
    declared = {e.get("target") for e in graph["edges"] if e.get("relation") == "contains"}
    reachable = [n for n in _nodes_by_label(graph, "TXForm") if n["id"] in declared]
    assert len(reachable) == 1
    assert str(reachable[0]["source_file"]).endswith("XFormP.pas")


def test_inherited_call_resolves_once_the_chain_is_repaired(tmp_path):
    """The compounding failure: pascal_inherited_calls walks the `inherits`
    chain, so a chain severed at its first link resolved no cross-file call."""
    graph = extract([BASE, DERIVED], cache_root=tmp_path, parallel=False)
    edge = _edge(graph, "calls", "Load()", "Refresh()")
    assert edge is not None
    target = next(n for n in graph["nodes"] if n["id"] == edge["target"])
    assert str(target["source_file"]).endswith("XFormP.pas")


def test_external_base_class_keeps_its_stub(tmp_path):
    """Fail closed: `TXForm` itself descends from `TForm`, which is RTL and not
    in the corpus. That edge must keep the stub it has today rather than
    acquire a guessed target."""
    graph = extract([BASE, DERIVED], cache_root=tmp_path, parallel=False)
    edge = _edge(graph, "inherits", "TXForm", "TForm")
    assert edge is not None
    declared = {e.get("target") for e in graph["edges"] if e.get("relation") == "contains"}
    assert edge["target"] not in declared


def test_resolver_does_not_change_list_lengths():
    """Incremental rebuilds hand resolvers scratch lists and keep only what was
    appended (`_rl_edges[_e0:]`), so a pass that adds or removes entries here
    would shift that slice and copy unrelated edges into the graph."""
    from graphify.pascal_class_resolution import resolve_pascal_base_classes

    nodes = [
        {"id": "base", "label": "TXForm", "source_file": "XFormP.pas"},
        {"id": "unit", "label": "XFormP", "source_file": "XFormP.pas"},
        {"id": "stub", "label": "TXForm", "source_file": "FillAkord.pas"},
        {"id": "derived", "label": "TfrmFillAkord", "source_file": "FillAkord.pas"},
    ]
    edges = [
        {"source": "unit", "target": "base", "relation": "contains"},
        {"source": "derived", "target": "stub", "relation": "inherits"},
    ]
    before_nodes, before_edges = len(nodes), len(edges)
    resolve_pascal_base_classes([], nodes, edges)
    assert len(nodes) == before_nodes
    assert len(edges) == before_edges
    assert edges[1]["target"] == "base"
