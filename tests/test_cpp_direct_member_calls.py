"""INC-QML-107: direct member bodies retain ordinary calls before canonicalization."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract_cpp
from graphify.extractors.cpp_member_identity import member_fact
from graphify.paths import load_node_link_graph
from graphify.source_relationships import logical_endpoints
from tests.cpp_same_unit_helpers import facade, members, native_calls, project, source, validate_span


def helper_edge(result, caller):
    """Exact source/callee identity excludes the unrelated Python helper fixture."""
    target, = [node for node in result["nodes"] if node["label"] == "helper()"
               and str(node.get("source_file", "")).endswith("panel.cpp")]
    return [edge for edge in result["edges"] if edge.get("relation") == "calls"
            and edge["source"] == caller["id"] and edge["target"] == target["id"]]


@pytest.mark.parametrize("marker", ["", "Q_INVOKABLE", "Q_SLOT"])
@pytest.mark.parametrize("namespace", ["", "Public"])
@pytest.mark.parametrize("owner", ["Panel", "Cpp"])
@pytest.mark.parametrize("profile", ["lf", "bom_crlf"])
def test_req_qml022_ac06_direct_actual_body_caller_keeps_source_call(tmp_path, marker, namespace, owner, profile):
    """The direct body keeps its allocated ID, while the facade selects the declaration.

    Original byte spans remain authoritative in both profiles. Ordinary call
    resolution does not expose an unannotated member to the native QML bridge.
    """
    raw = source(marker=marker, namespace=namespace, owner=owner).encode()
    if profile == "bom_crlf":
        raw = b"\xef\xbb\xbf// \xcf\x80 original\r\n" + raw.replace(b"\n", b"\r\n")
    path = project(tmp_path, marker=marker, namespace=namespace, owner=owner, raw=raw)
    direct = extract_cpp(path)
    found = members(direct)
    assert len(found) == 2 and len({node["id"] for node, _ in found}) == 2
    body, = [node for node, fact in found if fact["role"] == "definition"]
    assert not any(node.get("definition_file") for node, _ in found)
    (edge,) = helper_edge(direct, body)
    assert edge["confidence"] == "EXTRACTED" and edge["context"] == "cpp_free_function"
    for _, fact in found:
        assert validate_span(raw, fact)
    # Real public serialization retains the direct body endpoint; it must not
    # silently stamp canonical IDs merely to make source scope lookup work.
    graph = build_from_json(direct, root=tmp_path)
    output = tmp_path / "direct.json"
    assert to_json(graph, {}, str(output), force=True)
    restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    assert member_fact(restored.nodes[body["id"]])["role"] == "definition"
    assert any(logical_endpoints(restored, a, b, data) == (edge["source"], edge["target"])
               and data.get("relation") == "calls" for a, b, data in restored.edges(data=True))
    output.unlink()
    joined = facade(tmp_path)
    (canonical, proof), = members(joined)
    assert proof["role"] == "declaration" and canonical.get("definition_file") == "panel.cpp"
    assert len(helper_edge(joined, canonical)) == 1
    assert len(native_calls(joined)) == (1 if marker else 0)


def test_req_qml022_ac06_callback_return_method_preserves_direct_body_call(tmp_path):
    """A callback-returning method remains callable; the returned callback is not a provider."""
    raw = source().replace("void run();", "void (*run())(int);").replace(
        "void Panel::run() { helper(); }", "void (*Panel::run())(int) { helper(); return nullptr; }")
    path = tmp_path / "panel.cpp"
    path.write_bytes(raw.encode())
    result = extract_cpp(path)
    body, = [node for node, fact in members(result) if fact["role"] == "definition"]
    assert len(helper_edge(result, body)) == 1 and not body.get("definition_file")
