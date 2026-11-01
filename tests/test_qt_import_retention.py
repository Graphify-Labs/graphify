"""D33: graph-owned cleanup restrictions survive real graph transport boundaries."""
from __future__ import annotations

import copy
import json
import subprocess
import sys

import pytest

from graphify.build import build, build_from_json, build_merge, finalize_raw_graph_endpoints, merge_raw_extraction
from graphify.export import to_json
from graphify.paths import load_node_link_graph

FIELD = "qt_import_retention"


def payload():
    """A canonical unresolved import has no source/provider or authored origin."""
    return {"nodes": [{"id": "missing", "label": "missing", "file_type": "concept",
                       "type": "external", "external": True, "source_file": ""}],
            "links": [], "graph": {FIELD: {"schema": 1, "ids": ["missing"]}}}


@pytest.mark.parametrize("boundary", ["direct", "combined", "raw", "merge", "raw_merge", "json"])
def test_graph_owned_retention_crosses_actual_build_merge_and_reload(tmp_path, boundary):
    """All producers retain the restriction without promoting a placeholder's role."""
    data = payload()
    before = copy.deepcopy(data)
    path = tmp_path / "graph.json"
    if boundary in {"merge", "raw_merge"}:
        path.write_text(json.dumps(data), encoding="utf-8")
    if boundary == "direct":
        graph = build_from_json(data)
    elif boundary == "combined":
        graph = build([{**data, "edges": []}])
    elif boundary == "raw":
        finalize_raw_graph_endpoints(data)
        graph = load_node_link_graph(data)
    elif boundary == "merge":
        graph = build_merge([], graph_path=path, dedup=False)
    elif boundary == "raw_merge":
        data = merge_raw_extraction({"nodes": [], "edges": []}, path)
        finalize_raw_graph_endpoints(data)
        graph = load_node_link_graph(data)
    else:
        graph = load_node_link_graph(data)
        assert to_json(graph, {}, str(path))
        graph = load_node_link_graph(json.loads(path.read_text(encoding="utf-8")))
    assert graph.graph.get(FIELD) == before["graph"][FIELD]
    assert "missing" in graph and graph.degree("missing") == 0
    assert not graph.nodes["missing"].get("source_file")
    assert "_origin" not in graph.nodes["missing"]
    if boundary not in {"raw", "raw_merge"}:
        assert data == before, "Retention transport must not mutate borrowed metadata"


@pytest.mark.parametrize("corruption", ["scalar", "version", "bool_version", "extra", "ids_scalar",
                                       "duplicate", "unknown", "noncanonical", "role", "long", "limit"])
@pytest.mark.parametrize("boundary", ["direct", "combined", "raw", "merge", "raw_merge", "reload"])
def test_corrupt_retention_transport_cannot_authorize_a_graph_write(tmp_path, boundary, corruption):
    """Reserved malformed data fails safely rather than being dropped into cleanup."""
    data = payload()
    context = data["graph"][FIELD]
    if corruption == "scalar":
        data["graph"][FIELD] = "private-needle\nforged"
    elif corruption in {"version", "bool_version", "extra", "ids_scalar"}:
        key, value = {"version": ("schema", 2), "bool_version": ("schema", True),
                      "extra": ("private-needle", 1), "ids_scalar": ("ids", "missing")}[corruption]
        context[key] = value
    elif corruption in {"duplicate", "unknown", "noncanonical", "long", "limit"}:
        context["ids"] = {"duplicate": ["missing", "missing"], "unknown": ["absent"],
                          "noncanonical": ["Not-Canonical"], "long": ["x" * 4097],
                          "limit": ["missing"] * 100001}[corruption]
    else:
        data["nodes"][0]["source_file"] = "owned.py"
    before = copy.deepcopy(data)
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    prior = path.read_bytes()
    with pytest.raises(ValueError, match="QT_IMPORT_RETENTION_INVALID") as rejected:
        if boundary == "direct":
            build_from_json(data)
        elif boundary == "combined":
            build([{**data, "edges": []}])
        elif boundary == "raw":
            finalize_raw_graph_endpoints(data)
        elif boundary == "merge":
            build_merge([], graph_path=path)
        elif boundary == "raw_merge":
            merge_raw_extraction({"nodes": [], "edges": []}, path)
        else:
            load_node_link_graph(data)
    assert "private-needle" not in str(rejected.value)
    assert data == before and path.read_bytes() == prior


@pytest.mark.parametrize("force", [False, True])
def test_json_rejection_precedes_accounting_and_preserves_existing_bytes(tmp_path, force):
    """Direct export cannot silently consume a malformed reserved context."""
    import networkx as nx
    graph = nx.Graph()
    graph.add_node("missing", **{key: value for key, value in payload()["nodes"][0].items() if key != "id"})
    graph.graph.update({FIELD: "private-needle\nforged", "_dedup_collapsed": 3})
    before = copy.deepcopy(graph.graph)
    path = tmp_path / "graph.json"
    path.write_bytes(b"accepted bytes\r\n")
    with pytest.raises(ValueError, match="QT_IMPORT_RETENTION_INVALID") as rejected:
        to_json(graph, {}, str(path), force=force)
    assert "private-needle" not in str(rejected.value)
    assert graph.graph == before and path.read_bytes() == b"accepted bytes\r\n"


@pytest.mark.parametrize("first", ["graphify.paths", "graphify.build"])
def test_semantic_loader_deferred_role_dependency_has_no_import_cycle(first):
    """Both fresh-process orders validate actual valid and corrupt payloads."""
    source = f'''
import importlib, json
importlib.import_module({first!r})
from graphify.paths import load_node_link_graph
data = json.loads({json.dumps(payload())!r})
graph = load_node_link_graph(data)
assert graph.graph[{FIELD!r}] == {{"schema": 1, "ids": ["missing"]}}
data["graph"][{FIELD!r}]["ids"] = ["absent"]
try:
    load_node_link_graph(data)
except ValueError as error:
    assert str(error).startswith("QT_IMPORT_RETENTION_INVALID:")
else:
    raise AssertionError("corrupt context accepted")
'''
    result = subprocess.run([sys.executable, "-X", "utf8", "-c", source], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_policy_view_is_detached_and_role_transitions_are_producer_only():
    """A validated context can clear after a real role transition, without input mutation."""
    from graphify.build import _is_external_stub
    from graphify.qt_import_retention import apply_import_retention, read_import_retention
    data = payload()
    before = copy.deepcopy(data)
    ids = read_import_retention(data, is_placeholder=_is_external_stub)
    assert ids == frozenset({"missing"})
    result = apply_import_retention(data, ids, is_placeholder=_is_external_stub)
    result["graph"][FIELD]["ids"].append("independent")
    assert data == before
    # This producer view changes a real node role after validating the old view;
    # a transported record already carrying that mismatch must reject instead.
    changed = copy.deepcopy(data)
    changed["nodes"][0].update(type="class", external=False, source_file="defined.hpp", _origin="ast")
    assert FIELD not in apply_import_retention(changed, ids, is_placeholder=_is_external_stub).get("graph", {})
    with pytest.raises(ValueError, match="QT_IMPORT_RETENTION_INVALID"):
        read_import_retention(changed, is_placeholder=_is_external_stub)


@pytest.mark.parametrize("corruption", ["order", "duplicate_node", "bool_id", "surrogate", "wrong_slot"])
def test_remaining_context_integrity_boundaries_reject_without_inference(corruption):
    """Ordering, exact identities and the reserved location are validation, not repair."""
    from graphify.build import _is_external_stub
    from graphify.qt_import_retention import read_import_retention
    data = payload()
    if corruption == "order":
        data["nodes"].append({**data["nodes"][0], "id": "another", "label": "another"})
        data["graph"][FIELD]["ids"] = ["missing", "another"]
    elif corruption == "duplicate_node":
        data["nodes"].append(dict(data["nodes"][0]))
    elif corruption in {"bool_id", "surrogate"}:
        data["graph"][FIELD]["ids"] = [True if corruption == "bool_id" else "\ud800"]
    else:
        data[FIELD] = data["graph"].pop(FIELD)
    before = copy.deepcopy(data)
    with pytest.raises(ValueError, match="QT_IMPORT_RETENTION_INVALID"):
        read_import_retention(data, is_placeholder=_is_external_stub)
    assert data == before


def test_exact_count_and_utf8_budgets_preserve_boundary_then_reject(monkeypatch):
    """Limits count UTF-8 bytes and retained identities, never truncating to acceptance."""
    import graphify.qt_import_retention as policy
    from graphify.build import _is_external_stub
    assert policy.MAX_IDS == 100000 and policy.MAX_ID_BYTES == 4096
    monkeypatch.setattr(policy, "MAX_IDS", 2)
    monkeypatch.setattr(policy, "MAX_ID_BYTES", 8)
    data = payload()
    data["nodes"] = [{**data["nodes"][0], "id": value, "label": value} for value in ("a", "résumé")]
    data["graph"][FIELD]["ids"] = ["a", "résumé"]
    assert policy.read_import_retention(data, is_placeholder=_is_external_stub) == frozenset({"a", "résumé"})
    data["graph"][FIELD]["ids"].append("z")
    with pytest.raises(ValueError, match="QT_IMPORT_RETENTION_INVALID"):
        policy.read_import_retention(data, is_placeholder=_is_external_stub)
    data["graph"][FIELD]["ids"] = ["résumés"]
    with pytest.raises(ValueError, match="QT_IMPORT_RETENTION_INVALID"):
        policy.read_import_retention(data, is_placeholder=_is_external_stub)


def test_loader_captures_immutable_raw_policy_before_legacy_backfill(tmp_path):
    """Inferred AST provenance cannot retroactively authorize orphan retirement."""
    from graphify.build import _load_existing_graph
    data = payload()
    data["nodes"].append({"id": "backend", "label": "backend.cpp", "file_type": "code",
                          "source_file": "backend.cpp", "source_location": "L1", "_origin": "ast"})
    data["links"] = [{"source": "backend", "target": "missing", "relation": "imports", "context": "import",
                      "confidence": "EXTRACTED", "source_file": "backend.cpp", "source_location": "L1"}]
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    captured = {}
    loaded = _load_existing_graph(path, retention_policy=captured)
    assert loaded is not None and len(loaded) == 4
    assert loaded[1][0]["_origin"] == "ast"
    assert captured["ids"] == frozenset({"missing"})
    assert isinstance(captured["ids"], frozenset)


@pytest.mark.parametrize("boundary", ["direct", "combined", "reload"])
@pytest.mark.parametrize("graph_metadata", [None, False, 0, [], ""],
                         ids=["null", "false", "zero", "empty-list", "empty-string"])
def test_legacy_null_graph_without_reserved_context_remains_accepted(boundary, graph_metadata):
    """Exact installed 905 accepts falsy absence; it supplies no cleanup authority."""
    data = {"nodes": [], "edges": [], "graph": graph_metadata}
    if boundary == "direct":
        graph = build_from_json(data)
    elif boundary == "combined":
        graph = build([data])
    else:
        graph = load_node_link_graph(data)
    assert len(graph) == 0 and FIELD not in graph.graph


@pytest.mark.parametrize("case", ["graph", "nodes", "edges", "candidate_duplicate", "apply_budget", "plan_budget"])
def test_policy_rejects_malformed_producer_boundaries_without_partial_acceptance(monkeypatch, case):
    """Malformed groups, ambiguous candidate roles and overflow cannot erase a restriction."""
    from graphify.build import _is_external_stub
    import graphify.qt_import_retention as policy
    data = payload()
    if case == "graph":
        data["graph"] = "unsupported"
    elif case == "nodes":
        data["nodes"] = {}
    elif case == "edges":
        data["links"] = {}
    elif case == "candidate_duplicate":
        data["nodes"].append(dict(data["nodes"][0]))
    elif case == "apply_budget":
        monkeypatch.setattr(policy, "MAX_IDS", 0)
    else:
        data["graph"] = {}
        data["nodes"].append({"id": "backend", "label": "backend.cpp", "file_type": "code",
                              "source_file": "backend.cpp"})
        data["links"] = [{"source": "backend", "target": "missing"}]
        monkeypatch.setattr(policy, "MAX_IDS", 0)
    before = copy.deepcopy(data)
    with pytest.raises(ValueError, match="QT_IMPORT_RETENTION_INVALID"):
        if case in {"candidate_duplicate", "apply_budget"}:
            policy.apply_import_retention(data, {"missing"}, is_placeholder=_is_external_stub)
        else:
            policy.plan_import_retention(data, is_placeholder=_is_external_stub)
    assert data == before


def test_planner_ignores_irrelevant_untyped_records_without_granting_source_authority():
    """Transport noise supplies no source incidence, while an explicit restriction survives."""
    from graphify.build import _is_external_stub
    from graphify.qt_import_retention import plan_import_retention
    data = payload()
    data["nodes"].extend([None, {"id": ["invalid"]}])
    data["links"] = [None, {"source": ["not-an-identity"], "target": "missing"}]
    before = copy.deepcopy(data)
    assert plan_import_retention(data, is_placeholder=_is_external_stub) == frozenset({"missing"})
    assert data == before


@pytest.mark.parametrize("boundary", ["merge", "raw"])
@pytest.mark.parametrize("suffix", ["cpp", "py"])
def test_implicit_duplicate_native_candidate_rejects_and_repaired_merge_retries(tmp_path, boundary, suffix):
    """Absent reserved context cannot hide ambiguous native ownership; generic duplicates remain compatible."""
    data = payload()
    data["graph"] = {}
    data["nodes"].append(dict(data["nodes"][0]))
    data["nodes"].append({"id": "backend", "label": "backend", "file_type": "code",
                          "source_file": f"backend.{suffix}", "_origin": "ast"})
    data["links"] = [{"source": "backend", "target": "missing", "relation": "imports", "context": "import",
                      "source_file": f"backend.{suffix}", "confidence": "EXTRACTED", "_origin": "ast"}]
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    before = path.read_bytes()
    def merge():
        if boundary == "merge":
            return set(build_merge([], graph_path=path, dedup=False))
        return {node["id"] for node in merge_raw_extraction({"nodes": [], "edges": []}, path)["nodes"]}
    if suffix == "cpp":
        with pytest.raises(ValueError, match="QT_IMPORT_RETENTION_INVALID"):
            merge()
    else:
        assert merge() == {"backend", "missing"}
    assert path.read_bytes() == before
    data["nodes"].pop(1)
    path.write_text(json.dumps(data), encoding="utf-8")
    repaired = path.read_bytes()
    assert merge() == {"backend", "missing"} and path.read_bytes() == repaired
