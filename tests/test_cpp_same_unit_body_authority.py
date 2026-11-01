"""INC-QML-106: body navigation cannot substitute for strict actual call ownership."""
from __future__ import annotations

from copy import deepcopy

import pytest

import graphify.extractors.cpp_free_calls as free_calls
from graphify.extractors.cpp_member_identity import member_fact
from graphify.qt_declared_provider import DeclaredProviderIndex
from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.cpp_same_unit_helpers import facade, members, project, validate_span


@pytest.mark.parametrize("corruption", ["body_span", "body_owner", "body_role"])
def test_req_qml022_ac06_navigation_span_cannot_replace_actual_member_body_proof(tmp_path, monkeypatch, corruption):
    """Even matching navigation coordinates cannot rescue a corrupted actual producer proof."""
    source = project(tmp_path)
    original, snapshots = free_calls.resolve_free_function_calls, []

    def observe(nodes, edges, calls):
        if any(node.get("definition_span") and member_fact(node) for node in nodes):
            snapshots.append(deepcopy((nodes, edges, calls)))
        return original(nodes, edges, calls)

    with monkeypatch.context() as scope:
        scope.setattr(free_calls, "resolve_free_function_calls", observe)
        result = facade(tmp_path)
    assert snapshots
    nodes, edges, calls = snapshots[-1]
    call, = [call for call in calls if call.get("callee") == "helper" and call.get("cpp_free_call", {}).get("caller_native_family") == "member"]
    caller = next(node for node in nodes if node["id"] == call["caller_nid"])
    fact = call["cpp_free_call"]
    assert caller["definition_span"] == fact["caller_span"]
    assert b"Panel::run()" in validate_span(source.read_bytes(), {"span": caller["definition_span"]})
    proof = fact["caller_body_proof"]["fact"]
    if corruption == "body_span":
        proof["span"]["start_byte"] += 1
        proof["span"]["start_column"] += 1
    elif corruption == "body_owner":
        proof["owner_b64"] = "T3RoZXI="
    else:
        proof["role"] = "declaration"
    edges[:] = [edge for edge in edges if not (edge["source"] == caller["id"] and edge["relation"] == "calls")]
    original(nodes, edges, [call])
    assert not any(edge["source"] == caller["id"] and edge["relation"] == "calls" for edge in edges)
    # The same navigation hint cannot grant native API authority when the real
    # declaration carrier itself has become ambiguous.
    (member, _), = members(result)
    member["metadata"]["cpp_member"]["ambiguous"] = True
    declaration, = [node for node in result["nodes"] if qt_metadata(node).get("kind") == "member"
                    and qt_metadata(node).get("roles") == ["invokable"]]
    assert not DeclaredProviderIndex(result["nodes"]).source_owned(declaration)
