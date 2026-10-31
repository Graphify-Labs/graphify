"""INC-QML-99: source-owned free-call resolution cannot consume unknown partial callers."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract, extract_cpp
from graphify.paths import load_node_link_graph


CUDA = """int helper() { return 1; }
void kernel(int value) {}
int caller() {
 int value = helper();
 external();
 kernel<<<1, 1>>>(value);
 return value;
}
"""
PARTIAL = """int helper() { return 1; }
int caller() {
 int value = helper();
 external();
 broken( ;
 return value;
}
"""


def host_edge(result):
    caller = next(node for node in result["nodes"] if node["label"] == "caller()")
    helper = next(node for node in result["nodes"] if node["label"] == "helper()")
    return caller, helper, [edge for edge in result["edges"] if edge.get("relation") == "calls"
                            and edge["source"] == caller["id"] and edge["target"] == helper["id"]]


@pytest.mark.parametrize("suffix,source", [(".cu", CUDA), (".cpp", PARTIAL)], ids=["cuda", "partial-cpp"])
def test_req_qml022_ac06_partial_caller_retains_legacy_host_edge_raw_call_and_uncertainty(tmp_path, suffix, source):
    """No CUDA/compiler execution: the clean ordinary host call survives a marked partial parse."""
    path = tmp_path / ("partial" + suffix)
    path.write_text(source, encoding="utf-8")
    direct = extract_cpp(path)
    assert direct.get("parse_errors")
    caller, helper, edges = host_edge(direct)
    assert "cpp_function" not in caller.get("metadata", {})
    assert helper.get("metadata", {}).get("cpp_function")
    assert len(edges) == 1
    # Resolved local calls need no raw entry; the unresolved ordinary call does.
    raw = [call for call in direct["raw_calls"] if call.get("caller_nid") == caller["id"] and call.get("callee") == "external"]
    assert raw and not any(call.get("_cpp_free_deferred") or call.get("cpp_free_call") for call in raw)


@pytest.mark.parametrize("suffix,source", [(".cu", CUDA), (".cpp", PARTIAL)], ids=["cuda", "partial-cpp"])
def test_req_qml022_ac06_partial_host_call_survives_facade_cold_warm_and_export(tmp_path, suffix, source):
    """The source-only compatibility edge stays available through actual cache and durable transport."""
    path = tmp_path / ("partial" + suffix)
    path.write_text(source, encoding="utf-8")
    results = [extract([path], root=tmp_path, cache_root=tmp_path, parallel=False) for _ in range(2)]
    assert results[0] == results[1]
    for result in results:
        caller, helper, edges = host_edge(result)
        assert len(edges) == 1 and not result["failed_sources"]
        assert "cpp_function" not in caller.get("metadata", {})
        graph = build_from_json(result, root=tmp_path, directed=True)
        output = tmp_path / "accepted.json"
        assert to_json(graph, {}, str(output), force=True)
        loaded = load_node_link_graph(json.loads(output.read_text()))
        if loaded.is_multigraph():
            assert any(data.get("relation") == "calls" for data in loaded[caller["id"]][helper["id"]].values())
        else:
            assert loaded[caller["id"]][helper["id"]]["relation"] == "calls"


@pytest.mark.parametrize("kind,caller", [
    ("anonymous", "namespace { int caller(){return helper();} }"),
    ("conditional", "#if FEATURE\nint caller(){return helper();}\n#endif"),
    ("ambiguous", "int caller(){return helper();}\nint caller(){return helper();}"),
], ids=["anonymous", "conditional", "ambiguous"])
def test_req_qml022_ac06_recorded_uncertain_callers_cannot_regain_generic_free_label_guesses(tmp_path, kind, caller):
    """Caller uncertainty stays explicit; accepted namespace lookup never reverts to a legacy label guess."""
    path = tmp_path / "uncertain.cpp"
    path.write_text("int helper(){return 1;}\n" + caller, encoding="utf-8")
    result = extract_cpp(path)
    helper = next(node for node in result["nodes"] if node["label"] == "helper()")
    callers = [node for node in result["nodes"] if node["label"] == "caller()"]
    assert callers and all(node.get("metadata", {}).get("cpp_function") for node in callers)
    edges = [edge for edge in result["edges"] if edge.get("relation") == "calls" and edge["target"] == helper["id"]
             and edge["source"] in {node["id"] for node in callers}]
    if kind == "anonymous":
        assert not edges
    else:
        assert all(node["metadata"]["cpp_function"][kind] is True for node in callers)
        assert len(edges) == len(callers)
        assert all(edge["context"] == "cpp_free_function" and edge["confidence"] == "EXTRACTED" for edge in edges)
        owned = [call for call in result["raw_calls"] if call.get("caller_nid") in {node["id"] for node in callers}
                 and call.get("callee") == "helper" and call.get("cpp_free_call")]
        assert len(owned) == len(callers)


def test_req_qml022_ac06_accepted_native_member_and_constructor_callers_keep_free_calls(tmp_path):
    """Real source member/constructor proof remains eligible without a free-function record."""
    path = tmp_path / "native.cpp"
    path.write_text("int helper(){return 1;} class Owner{public:Owner(){helper();} void run(){helper();}};", encoding="utf-8")
    result = extract_cpp(path)
    helper = next(node for node in result["nodes"] if node["label"] == "helper()")
    edges = [edge for edge in result["edges"] if edge.get("relation") == "calls" and edge["target"] == helper["id"]]
    assert len(edges) == 2 and len({edge["source"] for edge in edges}) == 2


def test_req_qml022_ac06_owned_scoped_caller_keeps_its_exact_namespace_target(tmp_path):
    """The compatibility guard cannot route a fully owned call through the generic basename map."""
    path = tmp_path / "scoped.cpp"
    path.write_text("namespace First {int helper(){return 1;} int caller(){return helper();}}\n"
                    "namespace Second {int helper(){return 2;}}", encoding="utf-8")
    result = extract_cpp(path)
    caller = next(node for node in result["nodes"] if node["label"] == "caller()")
    target = next(node for node in result["nodes"] if node["label"] == "helper()" and node["source_location"] == "L1")
    assert [edge["target"] for edge in result["edges"] if edge.get("relation") == "calls" and edge["source"] == caller["id"]] == [target["id"]]


@pytest.mark.parametrize("target", ["#if FEATURE\nint helper(){return 1;}\n#endif",
                                    "int helper(){return 1;}\nint helper(){return 2;}"])
def test_req_qml022_ac06_owned_callers_still_reject_uncertain_target_definitions(tmp_path, target):
    """Partial-caller compatibility grants no new authority to conditional or duplicate targets."""
    path = tmp_path / "targets.cpp"
    path.write_text(target + "\nint caller(){return helper();}", encoding="utf-8")
    result = extract_cpp(path)
    caller = next(node for node in result["nodes"] if node["label"] == "caller()")
    assert caller.get("metadata", {}).get("cpp_function")
    assert not any(edge.get("relation") == "calls" and edge["source"] == caller["id"] for edge in result["edges"])
