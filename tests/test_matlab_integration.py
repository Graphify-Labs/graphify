"""Normal MATLAB dispatch, remap, and persisted-build integration coverage."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from graphify.build import build
from graphify.export import to_json
from graphify.extract import extract


def _extract(root: Path, paths: list[Path]) -> dict:
    return extract(paths, root=root, cache_root=root, parallel=False)


@pytest.mark.parametrize(("config", "name", "source", "expected_label"), [
    (
        "language.m=objc\n",
        "Mapped.m",
        "@interface Mapped : NSObject\n@end\n",
        "Mapped",
    ),
    (
        "language.m=python\n",
        "mapped.m",
        "def chosen():\n    return 1\n",
        "chosen()",
    ),
    (
        "language.inc=.m\n",
        "Mapped.inc",
        "@interface Mapped : NSObject\n@end\n",
        "Mapped",
    ),
])
def test_language_remaps_keep_matlab_and_objc_dispatch_contract(
    tmp_path: Path, config: str, name: str, source: str, expected_label: str,
) -> None:
    (tmp_path / ".graphifyrc").write_text(config, encoding="utf-8")
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")

    result = _extract(tmp_path, [path])

    assert any(node.get("label") == expected_label for node in result["nodes"])
    assert result["nodes"], "the selected remap must reach a real language extractor"


def test_matlab_calls_and_exact_source_inheritance_survive_build(tmp_path: Path) -> None:
    base = tmp_path / "Base.m"
    child = tmp_path / "Derived.m"
    calls = tmp_path / "Calls.m"
    base.write_text("classdef Base\nend\n", encoding="utf-8")
    child.write_text("classdef Derived < Base\nend\n", encoding="utf-8")
    calls.write_text(
        "function y = caller(x)\n"
        "    y = helper(x);\n"
        "end\n"
        "function y = helper(x)\n"
        "    y = x + 1;\n"
        "end\n",
        encoding="utf-8",
    )

    result = _extract(tmp_path, [base, child, calls])
    by_id = {node["id"]: node for node in result["nodes"]}
    raw_call = next(
        edge for edge in result["edges"]
        if edge.get("relation") == "calls"
        and by_id[edge["source"]].get("label") == "caller"
        and by_id[edge["target"]].get("label") == "helper"
    )
    raw_inherits = next(
        edge for edge in result["edges"]
        if edge.get("relation") == "inherits"
        and by_id[edge["source"]].get("label") == "Derived"
        and by_id[edge["target"]].get("label") == "Base"
    )
    assert raw_call.get("source_file") == "Calls.m"
    assert raw_call.get("source_location") == "L2"
    assert raw_inherits.get("source_file") == "Derived.m"

    graph = build([result], dedup=False, root=tmp_path)
    path = tmp_path / "built.json"
    assert to_json(graph, {}, str(path), force=True)
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored_nodes = {node["id"]: node for node in stored["nodes"]}
    stored_edges = stored.get("links", stored.get("edges", []))
    relations = {
        (stored_nodes[edge["source"]].get("label"),
         stored_nodes[edge["target"]].get("label"),
         edge.get("relation"), edge.get("source_file"), edge.get("source_location"))
        for edge in stored_edges
    }
    assert ("caller", "helper", "calls", "Calls.m", "L2") in relations
    assert ("Derived", "Base", "inherits", "Derived.m", "L1") in relations

def test_pre_upgrade_matlab_cache_does_not_mask_current_extraction(tmp_path, monkeypatch):
    from graphify import cache

    source = tmp_path / "controller.m"
    source.write_text("function value = controller(input)\n    value = input;\nend\n", encoding="utf-8")
    cache_root = tmp_path / "cache"
    current_schema = cache._AST_CACHE_SCHEMA
    # The pre-MATLAB AST cache namespace is the persisted schema-25 namespace.
    monkeypatch.setattr(cache, "_AST_CACHE_SCHEMA", 25)
    cache.save_cached(
        source,
        {"nodes": [{"id": "stale_cache_node", "label": "stale MATLAB parse",
                    "source_file": "controller.m"}], "edges": []},
        root=tmp_path,
        cache_root=cache_root,
    )
    monkeypatch.setattr(cache, "_AST_CACHE_SCHEMA", current_schema)

    result = extract([source], root=tmp_path, cache_root=cache_root, parallel=False)

    labels = {node.get("label") for node in result["nodes"]}
    assert "controller" in labels
    assert "stale MATLAB parse" not in labels
