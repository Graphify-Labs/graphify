"""#4909: binding references must not scan every edge for every import.

The #4854 pass rewrites a reference edge that points at a sourceless stub so it
points at the declaration in the imported file. Its first shape looped over the
whole edge list once per import fact, which made a full rebuild O(imports x
edges). This pins the lookup shape without timing anything: with E edges and I
imports, the pass must not resolve a path I x E times.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extractors import resolution
from graphify.extractors.base import _make_id
from graphify.extractors.models import _SymbolImportFact, _SymbolResolutionFacts


def test_reference_binding_scales_with_edges_not_imports(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "src.ts"
    source.write_text("", encoding="utf-8")
    target = tmp_path / "target.ts"
    target.write_text("", encoding="utf-8")

    n_facts = 8
    n_edges = 40
    nodes: list[dict] = []
    for i in range(n_edges):
        nodes.append({
            "id": f"stub{i}",
            "label": f"import{i}",
            "file_type": "code",
            "source_file": "",
        })
    for i in range(n_facts):
        nodes.append({
            "id": f"target{i}",
            "label": f"import{i}",
            "file_type": "code",
            "source_file": str(target),
        })

    source_id = _make_id(str(source))
    edges = [
        {
            "source": source_id,
            "target": f"stub{i}",
            "relation": "references",
            "source_file": str(source),
        }
        for i in range(n_edges)
    ]
    facts = _SymbolResolutionFacts(imports=[
        _SymbolImportFact(
            file_path=source,
            local_name=f"import{i}",
            target_path=target,
            imported_name=f"import{i}",
            line=i + 1,
        )
        for i in range(n_facts)
    ])

    calls = 0
    original = resolution._js_source_path

    def counting(path: str, root: Path) -> Path | None:
        nonlocal calls
        calls += 1
        return original(path, root)

    monkeypatch.setattr(resolution, "_js_source_path", counting)
    resolution._apply_symbol_resolution_facts(
        [source, target], nodes, edges, tmp_path, facts
    )

    # The lookups that depend on graph size are linear in nodes + edges. A
    # per-fact full scan is I x E and fails both bounds below.
    linear_budget = 4 * (len(nodes) + len(edges) + len(facts.imports))
    assert calls <= linear_budget, (
        f"{calls} path lookups for {n_facts} imports and {n_edges} edges; "
        f"linear budget is {linear_budget}"
    )
    assert calls < n_facts * n_edges

    for i in range(n_facts):
        assert edges[i]["target"] == f"target{i}"
    for i in range(n_facts, n_edges):
        assert edges[i]["target"] == f"stub{i}"
