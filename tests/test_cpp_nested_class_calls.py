"""INC-QML-109: enclosing classes own name lookup without becoming namespaces."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.cpp_class_proof import class_fact
from graphify.extractors.cpp_functions import decoded, free_definition_fact
from graphify.paths import load_node_link_graph
from graphify.source_relationships import logical_endpoints
from tests.cpp_nested_helpers import nested_source, produce, source_call_edges
from tests.cpp_same_unit_helpers import validate_span


@pytest.mark.parametrize("mode", ["direct", "facade"])
@pytest.mark.parametrize("shadow,inherited", [
    ("static void (*helper)();", False), ("static void helper();", False),
    ("static int helper;", False), ("int helper;", False), ("", True),
])
@pytest.mark.parametrize("namespace,depth", [("", 1), ("Public", 2)])
def test_req_qml022_ac06_enclosing_class_members_hide_free_functions(tmp_path, mode, shadow, inherited, namespace, depth):
    """An actual lexical parent or its base blocks global and namespace namesakes."""
    raw = nested_source(shadow=shadow, inherited=inherited, namespace=namespace, depth=depth)
    result = produce(tmp_path, raw, mode=mode)
    assert not source_call_edges(result)
    for node in result["nodes"]:
        if fact := class_fact(node):
            assert validate_span(raw, fact)


@pytest.mark.parametrize("mode", ["direct", "facade"])
@pytest.mark.parametrize("namespace,shadow,call", [
    ("", "", "helper()"), ("Public", "", "helper()"),
    ("", "static void (*helper)();", "::helper()"),
    ("", "static void helper();", "::helper()"),
    ("Public", "static void helper();", "::Public::helper()"),
    ("Public", "static void helper();", "Public::helper()"),
])
@pytest.mark.parametrize("profile", ["lf", "bom_crlf"])
def test_req_qml022_ac06_nested_namespace_and_explicit_lookup_keep_real_calls(tmp_path, mode, namespace, shadow, call, profile):
    """Class ancestry removes class spellings only; explicit qualification bypasses hiding."""
    raw = nested_source(namespace=namespace, shadow=shadow, call=call, depth=2)
    if profile == "bom_crlf":
        raw = b"\xef\xbb\xbf// \xcf\x80 original\r\n" + raw.replace(b"\n", b"\r\n")
    result = produce(tmp_path, raw, mode=mode, filename="outer.cpp")
    edge, = source_call_edges(result)
    assert edge["confidence"] == "EXTRACTED" and edge["context"] == "cpp_free_function"
    target, = [node for node in result["nodes"] if node["id"] == edge["target"]]
    assert decoded(free_definition_fact(target)["qualified_name_b64"]) == "::".join(filter(None, (namespace, "helper")))
    # Persisted direction and the actual direct/canonical caller survive the
    # public graph assembly and loader, with no fabricated class-namespace edge.
    graph = build_from_json(result, root=tmp_path)
    output = tmp_path / "saved.json"
    assert to_json(graph, {}, str(output), force=True)
    restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    assert any(logical_endpoints(restored, a, b, data) == (edge["source"], edge["target"])
               and data.get("relation") == "calls" for a, b, data in restored.edges(data=True))


@pytest.mark.parametrize("mode", ["direct", "facade"])
def test_req_qml022_ac06_source_proven_member_owner_usings_keep_explicit_free_call(tmp_path, mode):
    """Existing literal member-owner joins remain valid without guessing unqualified using lookup."""
    raw = nested_source(namespace="Public", call="::Public::helper()")
    body = b"void Outer::Inner::run(){::Public::helper();}\n"
    assert body in raw
    raw = raw.replace(body, b"") + b"using namespace Public;\n" + body
    result = produce(tmp_path, raw, mode=mode)
    edge, = source_call_edges(result)
    target, = [node for node in result["nodes"] if node["id"] == edge["target"]]
    assert decoded(free_definition_fact(target)["qualified_name_b64"]) == "Public::helper"


@pytest.mark.parametrize("mode", ["direct", "facade"])
@pytest.mark.parametrize("shadow,expected", [("", 1), ("static void helper();", 0), ("static void (*helper)();", 0)])
def test_req_qml022_ac06_inline_nested_body_uses_the_same_source_class_ancestry(tmp_path, mode, shadow, expected):
    """Inline ownership does not bypass lexical parents or invent an out-of-line body proxy."""
    raw = nested_source(namespace="Public", shadow=shadow)
    raw = raw.replace(b"void Outer::Inner::run(){helper();}\n", b"")
    raw = raw.replace(b"void run();", b"void run(){helper();}")
    result = produce(tmp_path, raw, mode=mode)
    assert len(source_call_edges(result)) == expected
