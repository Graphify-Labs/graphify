"""INC-QML-106: same-unit declaration/body facts keep actual allocated ownership."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract_cpp
from graphify.extractors.cpp_member_identity import member_fact
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from tests.cpp_same_unit_helpers import call_sites, class_node, decoded, facade, members, native_calls, project, source, validate_span


@pytest.mark.parametrize("marker", ["", "Q_INVOKABLE", "Q_SLOT"])
@pytest.mark.parametrize("namespace", ["", "Public"])
@pytest.mark.parametrize("bom,newline", [("", "\n"), ("\ufeff// π original\n", "\r\n")])
def test_req_qml022_ac02_direct_same_unit_members_keep_both_original_occurrences(tmp_path, marker, namespace, bom, newline):
    """The actual body allocator cannot overwrite its neighboring prototype's proof."""
    raw = (bom + source(marker=marker, namespace=namespace)).replace("\n", newline).encode()
    path = tmp_path / "panel.cpp"
    path.write_bytes(raw)
    result = extract_cpp(path)
    facts = members(result)
    assert len(facts) == 2
    assert {fact["role"] for _, fact in facts} == {"declaration", "definition"}
    assert len({node["id"] for node, _ in facts}) == 2
    assert len({fact["signature"] for _, fact in facts}) == 1
    expected_owner = namespace + "::Panel" if namespace else "Panel"
    for node, fact in facts:
        assert decoded(fact, "owner_b64") == expected_owner and not fact["ambiguous"]
        fragment = validate_span(raw, fact)
        assert decoded(fact, "name_b64") == node["label"].removeprefix(".").removesuffix("()")
        if fact["role"] == "definition":
            assert b"Panel::run()" in fragment and b"helper();" in fragment
        else:
            assert fragment == b"void run();"


@pytest.mark.parametrize("marker,exposed", [("", False), ("Q_INVOKABLE", True), ("Q_SLOT", True)])
@pytest.mark.parametrize("owner", ["Panel", "Cpp"])
@pytest.mark.parametrize("directed", [False, True])
def test_req_qml022_ac02_same_unit_canonical_member_and_native_endpoint_roundtrip(tmp_path, marker, exposed, owner, directed):
    """A proved pair retains one declaration identity/body navigation and exact exposure."""
    raw = ("\ufeff// π original\n" + source(marker=marker, owner=owner)).replace("\n", "\r\n").encode()
    project(tmp_path, marker=marker, owner=owner, raw=raw)
    result = facade(tmp_path)
    (member, fact), = members(result)
    actual_class = class_node(result)
    assert fact["role"] == "declaration" and member["label"] == ".run()"
    assert member["definition_file"] == "panel.cpp"
    lines = raw[:raw.index(f"void {owner}::run()".encode())].count(b"\n") + 1
    assert member["definition_location"] == f"L{lines}"
    assert any(edge["source"] == actual_class["id"] and edge["target"] == member["id"]
               and edge["relation"] == "method" for edge in result["edges"])
    helper, = [node for node in result["nodes"] if node["source_file"] == "panel.cpp" and node["label"] == "helper()"]
    assert any(edge["source"] == member["id"] and edge["target"] == helper["id"] and edge["relation"] == "calls" for edge in result["edges"])
    if owner == "Cpp":
        # This actual class collides with panel.cpp's file ID before allocation.
        assert actual_class["id"] != "panel_cpp" and member["id"].startswith(actual_class["id"] + "_")
    calls = native_calls(result)
    if exposed:
        (call,) = calls
        assert call["target"] == member["id"]
        proof = qt_metadata(call)["native_endpoint"]
        assert proof["canonical_target_id"] == member["id"] and proof["class_id"] == actual_class["id"]
    else:
        assert not calls and call_sites(result)[0]["status"] != "resolved"
    graph = build_from_json(result, root=tmp_path, directed=directed)
    output = tmp_path / "accepted.json"
    assert to_json(graph, {}, str(output), force=True)
    restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    assert restored.nodes[member["id"]]["metadata"] == member["metadata"]
    assert member_fact(restored.nodes[member["id"]]) == fact
    assert restored.nodes[member["id"]]["definition_location"] == member["definition_location"]
