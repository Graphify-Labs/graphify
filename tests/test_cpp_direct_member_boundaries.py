"""INC-QML-107: direct scope proxies preserve lexical and source-proof barriers."""
from __future__ import annotations

import json

import pytest

from graphify.extract import extract_cpp
from graphify.extractors.cpp_free_calls import resolve_free_function_calls
from graphify.extractors.cpp_member_identity import member_fact, proven_member_pairs
from graphify.extractors.cpp_functions import decoded, free_definition_fact
from tests.cpp_same_unit_helpers import members, source
from tests.test_cpp_direct_member_calls import helper_edge


def extracted(root, raw):
    path = root / "panel.cpp"
    path.write_bytes(raw.encode())
    result = extract_cpp(path)
    assert not result.get("error")
    return result


@pytest.mark.parametrize("declarations,body,prefix", [
    ("void (*helper)();", "helper();", ""),
    ("void helper();", "helper();", ""),
    ("void helper(int);", "helper();", ""),
    ("", "void (*helper)()=nullptr; helper();", ""),
    ("", "using helper=Unknown; helper();", ""),
    ("", "helper();", "class Base {public:void (*helper)();};"),
])
def test_req_qml022_ac06_direct_proxy_keeps_actual_member_and_local_shadowing(tmp_path, declarations, body, prefix):
    """A real declaration ID supplies class hiding; storage never resolves to a free target."""
    raw = source(declarations=declarations, prefix=prefix).replace("void helper() {}", "void helper() {}\nvoid other() {}")
    if prefix:
        raw = raw.replace("public QObject", "public Base")
    raw = raw.replace("helper(); }", body + " other(); }")
    result = extracted(tmp_path, raw)
    caller, = [node for node, fact in members(result) if fact["role"] == "definition" and "run" in node["label"]]
    assert not helper_edge(result, caller)
    other, = [node for node in result["nodes"] if node["label"] == "other()"]
    assert any(edge["source"] == caller["id"] and edge["target"] == other["id"]
               and edge["relation"] == "calls" for edge in result["edges"])


@pytest.mark.parametrize("case", ["conditional_body", "conditional_prototype", "cv_mismatch", "ref_mismatch",
                                   "duplicate_body", "duplicate_prototype", "foreign_owner", "overload"])
def test_req_qml022_ac06_unproved_direct_member_scope_cannot_borrow_a_class(tmp_path, case):
    """The new direct view keeps the same source-pair rejection profile as canonicalization."""
    raw = source()
    if case == "conditional_body":
        raw = raw.replace("void Panel::run() { helper(); }", "#if FEATURE\nvoid Panel::run() { helper(); }\n#endif")
    elif case == "conditional_prototype":
        raw = raw.replace("Q_INVOKABLE void run();", "#if FEATURE\nQ_INVOKABLE void run();\n#endif")
    elif case == "cv_mismatch":
        raw = raw.replace("void run();", "void run() const;")
    elif case == "ref_mismatch":
        raw = raw.replace("void run();", "void run() &;").replace("Panel::run()", "Panel::run() &&")
    elif case == "duplicate_body":
        raw += "void Panel::run() { helper(); }\n"
    elif case == "duplicate_prototype":
        raw = raw.replace("void run();", "void run(); void run();")
    elif case == "foreign_owner":
        raw = raw.replace("Panel::run()", "Other::run()")
    else:
        raw = raw.replace("void run();", "void run(int); void run(double);").replace("Panel::run()", "Panel::run(int)")
    result = extracted(tmp_path, raw)
    assert not proven_member_pairs(result["nodes"], result["edges"])
    assert not [edge for edge in result["edges"] if edge.get("relation") == "calls"]


@pytest.mark.parametrize("corruption", ["body_span", "body_ambiguous", "call_signature", "caller_id", "contains",
                                       "method", "class", "class_ambiguous", "shadowed", "unevaluated"])
def test_req_qml022_ac06_direct_scope_rejects_corrupt_or_unavailable_actual_ownership(tmp_path, corruption):
    """Real producer transport is replayed through the public resolver after one proof is damaged."""
    result = json.loads(json.dumps(extracted(tmp_path, source())))
    body, = [node for node, fact in members(result) if fact["role"] == "definition"]
    declaration, = [node for node, fact in members(result) if fact["role"] == "declaration"]
    call, = [call for call in result["raw_calls"] if call.get("cpp_free_call") and call["callee"] == "helper"]
    result["edges"][:] = [edge for edge in result["edges"] if edge.get("relation") != "calls"]
    if corruption == "body_span":
        body["metadata"]["cpp_member"]["span"]["start_column"] += 1
    elif corruption == "body_ambiguous":
        body["metadata"]["cpp_member"]["ambiguous"] = True
    elif corruption == "call_signature":
        call["cpp_free_call"]["caller_native_signature"] = "0" * 64
    elif corruption == "caller_id":
        call["caller_nid"] = declaration["id"]
    elif corruption in {"contains", "method"}:
        target = body["id"] if corruption == "contains" else declaration["id"]
        for edge in result["edges"]:
            if edge["target"] == target and edge.get("relation") == corruption:
                edge["confidence"] = "INFERRED"
    elif corruption in {"class", "class_ambiguous"}:
        owner, = [node for node in result["nodes"] if node.get("_callable_class")]
        owner["metadata"]["cpp_class"]["is_definition" if corruption == "class" else "ambiguous"] = corruption != "class"
    else:
        call["cpp_free_call"][corruption] = True
    resolve_free_function_calls(result["nodes"], result["edges"], result["raw_calls"])
    assert not helper_edge(result, body)


def test_req_qml022_ac06_namespace_free_body_is_not_relabelled_as_a_native_member(tmp_path):
    """A namespace function's own source proof remains the owner despite a class namesake method."""
    result = extracted(tmp_path, "namespace Public {void helper(){} void run(){helper();}} class Other{public:void run();};")
    caller, = [node for node in result["nodes"] if decoded(free_definition_fact(node).get("qualified_name_b64")) == "Public::run"]
    helper, = [node for node in result["nodes"] if decoded(free_definition_fact(node).get("qualified_name_b64")) == "Public::helper"]
    assert free_definition_fact(caller) and not member_fact(caller)
    assert any(edge["source"] == caller["id"] and edge["target"] == helper["id"]
               and edge["relation"] == "calls" for edge in result["edges"])
