"""INC-QML-73: exact source bodies survive canonical member/constructor joins."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from graphify.extract import extract
import graphify.extractors.cpp_free_calls as free_calls


def canonical_body_snapshot(tmp_path, monkeypatch):
    """Observe the actual final resolver input, without replacing its behavior."""
    header = tmp_path / "backend.h"
    implementation = tmp_path / "backend.cpp"
    header.write_bytes(b"\xef\xbb\xbf// caf\xc3\xa9\r\nclass Backend{public:Backend();Backend(int);int work();};\r\n")
    raw = (b'\xef\xbb\xbf// caf\xc3\xa9\r\n#include "backend.h"\r\nint helper(){return 1;}\r\n'
           b'Backend::Backend(){helper();}\r\nBackend::Backend(int value){helper();}\r\nint Backend::work(){return helper();}\r\n')
    implementation.write_bytes(raw)
    actual, captured = free_calls.resolve_free_function_calls, []

    def observe(nodes, edges, calls):
        if any(node.get("definition_file") and node.get("metadata", {}).get("cpp_member") for node in nodes):
            captured.append(deepcopy((nodes, edges, calls)))
        return actual(nodes, edges, calls)

    with monkeypatch.context() as scope:
        scope.setattr(free_calls, "resolve_free_function_calls", observe)
        result = extract([header, implementation], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result["failed_sources"] and not result["qml_failures"]
    assert captured
    # Exercise a real JSON transport, retaining exact numeric/span types.
    nodes, edges, calls = json.loads(json.dumps(captured[-1]))
    return nodes, [edge for edge in edges if edge["relation"] != "calls"], calls, raw


def test_req_qml022_ac06_original_member_body_and_two_constructor_bodies_keep_calls(tmp_path, monkeypatch):
    """Original BOM/CRLF bytes independently prove each body span before call rebuilding."""
    nodes, edges, calls, source = canonical_body_snapshot(tmp_path, monkeypatch)
    owned = [call for call in calls if call.get("cpp_free_call") and call["callee"] == "helper"]
    assert len(owned) == 3
    for call in owned:
        fact = call["cpp_free_call"]
        span = fact["caller_span"]
        fragment = source[span["start_byte"]:span["end_byte"]]
        assert b"Backend::" in fragment and fragment.endswith(b"}")
        assert fact["span"]["start_byte"] >= span["start_byte"]
        if fact["caller_native_family"] == "member":
            assert fact["caller_body_proof"]["fact"]["span"] == span
    free_calls.resolve_free_function_calls(nodes, edges, calls)
    assert len([edge for edge in edges if edge["relation"] == "calls"]) == 3


@pytest.mark.parametrize("corruption", ["family", "signature", "span", "body_span", "body_owner", "body_role",
                                       "body_role_list", "body_role_dict", "definition_path", "containment"])
def test_req_qml022_ac06_canonical_member_body_rejects_corrupt_source_proof(tmp_path, monkeypatch, corruption):
    """A declaration line/signature cannot replace the original body and accepted file ownership."""
    nodes, edges, calls, _ = canonical_body_snapshot(tmp_path, monkeypatch)
    call = next(call for call in calls if call.get("cpp_free_call", {}).get("caller_native_family") == "member")
    fact, caller_id = call["cpp_free_call"], call["caller_nid"]
    caller = next(node for node in nodes if node["id"] == caller_id)
    if corruption == "family":
        fact["caller_native_family"] = "constructor"
    elif corruption == "signature":
        fact["caller_native_signature"] = "0" * 64
    elif corruption == "span":
        fact["caller_span"]["start_byte"] += 1
        fact["caller_span"]["start_column"] += 1
    elif corruption == "body_span":
        fact["caller_body_proof"]["fact"]["span"]["start_byte"] += 1
        fact["caller_body_proof"]["fact"]["span"]["start_column"] += 1
    elif corruption == "body_owner":
        fact["caller_body_proof"]["fact"]["owner_b64"] = "T3RoZXI="
    elif corruption.startswith("body_role"):
        fact["caller_body_proof"]["fact"]["role"] = [] if corruption.endswith("list") else {} if corruption.endswith("dict") else "declaration"
    elif corruption == "definition_path":
        caller["definition_file"] = "other.cpp"
    else:
        edges[:] = [edge for edge in edges if not (edge["target"] == caller_id and edge["relation"] == "contains")]
    free_calls.resolve_free_function_calls(nodes, edges, calls)
    assert not any(edge["relation"] == "calls" and edge["source"] == caller_id for edge in edges)
    assert len([edge for edge in edges if edge["relation"] == "calls"]) == 2
