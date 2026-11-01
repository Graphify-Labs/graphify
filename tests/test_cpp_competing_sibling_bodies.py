"""INC-QML-106: two admitted sibling bodies do not prove one definition site."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract_cpp
from graphify.extractors.cpp_member_identity import member_fact
from graphify.extractors.resolution import _merge_decl_def_classes
from graphify.paths import load_node_link_graph
from tests.cpp_same_unit_helpers import facade, members, validate_span


def test_req_qml022_ac06_competing_sibling_bodies_preserve_each_original_occurrence(tmp_path):
    """Actual .cpp/.cc alternatives retain separate IDs and no chosen body navigation.

    The header declaration remains a valid source fact. Multiple implementations
    prevent a unique definition join; this does not assert compiler/ODR behavior
    or revoke the independently accepted declaration's native API authority.
    """
    sources = {
        "Panel.h": b"class Panel { public: void run(); };\n",
        "Panel.cpp": b'#include "Panel.h"\nvoid Panel::run() {}\n',
        "Panel.cc": b'#include "Panel.h"\nvoid Panel::run() {}\n',
    }
    direct = []
    for name, raw in sources.items():
        path = tmp_path / name
        path.write_bytes(raw)
        result = extract_cpp(path)
        assert not result.get("error") and not result.get("qt_failures")
        direct.extend(members(result))
    assert len(direct) == 3
    # Sibling extensions intentionally share a pre-facade stem ID. Distinct
    # source occurrences, rather than that shared ID, prove the competition.
    definitions = {Path(node["source_file"]).name: fact for node, fact in direct if fact["role"] == "definition"}
    assert len(definitions) == 2 and all(not fact["ambiguous"] for fact in definitions.values())

    result = facade(tmp_path)
    found = members(result)
    assert len(found) == 3 and len({node["id"] for node, _ in found}) == 3
    assert {node["source_file"] for node, fact in found if fact["role"] == "definition"} == {"Panel.cpp", "Panel.cc"}
    assert not any(node.get("definition_file") or node.get("definition_span") for node, _ in found)
    assert not any(fact.get("bound_owner_b64") for _, fact in found)
    for node, fact in found:
        assert validate_span(sources[node["source_file"]], fact).startswith(b"void ")
        if fact["role"] == "definition":
            assert fact == definitions[node["source_file"]]
    # Assembly and public reload must retain both unselected implementation
    # occurrences rather than choosing whichever input happened to be visited.
    graph = build_from_json(result, root=tmp_path)
    output = tmp_path / "accepted.json"
    assert to_json(graph, {}, str(output), force=True)
    restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    for node, fact in found:
        assert member_fact(restored.nodes[node["id"]]) == fact
        assert not restored.nodes[node["id"]].get("definition_file")


def test_req_qml008_ac02_duplicate_representation_of_one_body_retains_unique_join(tmp_path):
    """Fresh and accepted-context copies describe one original source occurrence.

    Feed the real production merger actual direct-producer nodes and extracted
    edges. Repeating the same complete body must not manufacture ambiguity or
    disable the unique header/implementation join.
    """
    header, implementation = tmp_path / "Panel.h", tmp_path / "Panel.cpp"
    header.write_bytes(b"class Panel { public: void run(); };\n")
    implementation.write_bytes(b'#include "Panel.h"\nvoid Panel::run() {}\n')
    declaration, body = extract_cpp(header), extract_cpp(implementation)
    assert not declaration.get("error") and not body.get("error")
    (body_node, body_fact), = members(body)
    nodes = deepcopy(declaration["nodes"] + body["nodes"] + [body_node])
    edges = deepcopy(declaration["edges"] + body["edges"] + body["edges"])
    calls = deepcopy(declaration.get("raw_calls", []) + body.get("raw_calls", []))
    _merge_decl_def_classes(nodes, edges, calls)
    (joined, proof), = members({"nodes": nodes})
    assert joined["source_file"] == str(header) and proof["role"] == "declaration"
    assert joined["definition_file"] == str(implementation) and joined["definition_location"] == "L2"
    assert validate_span(implementation.read_bytes(), body_fact) == b"void Panel::run() {}"
    assert not proof["ambiguous"]
