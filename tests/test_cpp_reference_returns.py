"""REQ-QML-018-AC02/AC03 canonical generic reference-return declarations."""
import json

import pytest

from graphify.affected import affected_nodes
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract_cpp
from graphify.extractors.engine import _get_cpp_func_name
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_syntax import read_cpp, walk
from graphify.paths import load_node_link_graph
from graphify.serve import _query_graph_text
from tests.qt_adoption_fixture import NATIVE, sources
from tests.qt_analysis_helpers import analysis, sites


@pytest.mark.parametrize("result_type", ["Backend &", "Backend &&", "Backend", "Backend *"])
def test_req_qml018_ac02_ac03_reference_return_has_canonical_callable(tmp_path, result_type):
    """Generic producer owns the declaration; the provider lends its declared API."""
    native = NATIVE.replace("Backend *makeBackend()", result_type + " makeBackend()")
    result = analysis(tmp_path, sources(tmp_path, native=native))
    member = next(node for node in sites(result, "member") if qt_metadata(node)["raw_name"] == "makeBackend")
    target = qt_metadata(member)["generic_target_id"]
    assert target
    direct = extract_cpp(tmp_path / "native.h")
    direct_members = [node for node in direct["nodes"] if node.get("_callable") and node["label"] == ".makeBackend()"]
    assert len(direct_members) == 1
    by_id = {node["id"]: node for node in result["nodes"]}
    assert by_id[target]["label"] == ".makeBackend()" and by_id[target]["_callable"]
    if result_type in {"Backend &", "Backend *"}:
        assert len(sites(result, "context_binding")) == 1
        assert sites(result, "context_access") and len(sites(result, "context_subscription")) == 2
    else:
        # Generic callable admission does not widen the one-object provider
        # profile to value temporaries or unsupported rvalue references.
        assert not sites(result, "context_binding")


@pytest.mark.parametrize("result_type", ["Backend &", "Backend &&", "const Backend &", "Backend *", "Backend"])
def test_req_qml018_ac02_qualified_reference_declaration_and_definition_keep_one_callable(tmp_path, result_type):
    """Wrapping the actual function declarator preserves full names and canonical joins."""
    header = "namespace Public { class Backend {}; class Factory { public: " + result_type + " create(); }; }\n"
    body = '#include "native.h"\n' + result_type.replace("Backend", "Public::Backend") + " Public::Factory::create() { throw 7; }\n"
    result = analysis(tmp_path, {"native.h": header, "native.cpp": body})
    candidates = [node for node in result["nodes"] if node.get("_callable") and node.get("label") == ".create()"]
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["source_file"] == "native.h" and candidate["definition_file"] == "native.cpp"
    for name in ["native.h", "native.cpp"]:
        unit = read_cpp(tmp_path / name, tmp_path)
        declarators = [node for node in walk(unit.root) if node.type == "function_declarator"]
        assert len(declarators) == 1
        outer = declarators[0].parent
        value = _get_cpp_func_name(outer, unit.source)
        assert value == ("create" if name.endswith(".h") else "Public::Factory::create")


@pytest.mark.parametrize("directed", [False, True])
def test_req_qml018_ac02_ac03_reference_provider_spans_and_consumers_survive_reload(tmp_path, directed):
    """Original BOM/CRLF/Unicode bytes and typed-provider evidence reach durable consumers."""
    native = ("\ufeff// café 雪\n" + NATIVE.replace("Backend *makeBackend()", "Backend &makeBackend()")).replace("\n", "\r\n")
    result = analysis(tmp_path, sources(tmp_path, native=native))
    member = next(node for node in sites(result, "member") if qt_metadata(node)["raw_name"] == "makeBackend")
    metadata = qt_metadata(member)
    span = metadata["span"]
    assert (tmp_path / "native.h").read_bytes()[span["start_byte"]:span["end_byte"]] == b"Backend &makeBackend() { throw 7; }"
    graph = build_from_json(result, root=tmp_path, directed=directed)
    path = tmp_path / "graph.json"
    assert to_json(graph, {}, str(path))
    reloaded = load_node_link_graph(json.loads(path.read_text(encoding="utf-8")))
    assert metadata["generic_target_id"] in reloaded
    assert qt_metadata(reloaded.nodes[member["id"]]) == metadata
    accesses = sites(result, "context_access")
    assert accesses and len(sites(result, "context_subscription")) == 2
    for access in accesses:
        md = qt_metadata(reloaded.nodes[access["id"]])
        assert md["status"] == "resolved" and md["endpoint_proof"]["canonical_target_id"] in reloaded
        assert not any(data.get("relation") == "calls" for _, _, data in reloaded.edges(access["id"], data=True)
                       if data.get("context") == "qt_context_subscription")
    assert "Main.qml" in _query_graph_text(reloaded, "backend service refresh", token_budget=4000)
    access = next(node for node in accesses if qt_metadata(node)["endpoint_proof"]["kind"] == "function")
    terminal = qt_metadata(access)["endpoint_proof"]["canonical_target_id"]
    if directed:
        assert reloaded.has_edge(access["id"], terminal)
        assert any(hit.node_id == access["id"] for hit in affected_nodes(reloaded, terminal, depth=3))
    else:
        edge = reloaded.edges[access["id"], terminal]
        assert (edge["_src"], edge["_tgt"]) == (access["id"], terminal)
    # INC-QML-30 separately owns affected's undirected logical direction;
    # the persisted producer/consumer edge here retains its exact endpoints.


def test_req_qml018_ac02_reference_fallback_requires_one_function_child():
    """Malformed or competing grammar children cannot supply an arbitrary callable name."""
    class Syntax:
        def __init__(self, kind, children=(), name=None):
            self.type, self.children, self.name = kind, children, name

        def child_by_field_name(self, field):
            return self.name if field == "declarator" else None

    # The real grammar defect is covered above. This isolated malformed-node
    # guard checks fallback shape without inventing extraction behavior in a fake.
    children = [Syntax("function_declarator"), Syntax("function_declarator")]
    assert _get_cpp_func_name(Syntax("reference_declarator", children), b"") is None
    assert _get_cpp_func_name(Syntax("reference_declarator", [Syntax("type_identifier")]), b"") is None


def test_req_qml018_ac03_unproven_factory_overloads_stay_unavailable(tmp_path):
    """Reference admission does not authorize ambiguous callable selection."""
    native = NATIVE.replace("Backend *makeBackend() { throw 7; }", "Backend &makeBackend(); Service &makeBackend();")
    result = analysis(tmp_path, sources(tmp_path, native=native))
    assert not sites(result, "context_binding")
    assert not sites(result, "context_access")


def test_req_qml018_ac03_const_reference_retains_original_declared_api_shape(tmp_path):
    """Static declared surface retains CV without proving a runtime QObject conversion."""
    result = analysis(tmp_path, sources(tmp_path, native=NATIVE.replace("Backend *makeBackend()", "const Backend &makeBackend()")))
    member = next(node for node in sites(result, "member") if qt_metadata(node)["raw_name"] == "makeBackend")
    metadata = qt_metadata(member)
    assert metadata["generic_target_id"]
    assert metadata["api_type_spelling"] == "const Backend &"
    assert metadata["api_type_status"] == "resolved"
    assert len(sites(result, "context_binding")) == 1
    assert sites(result, "context_access") and len(sites(result, "context_subscription")) == 2
