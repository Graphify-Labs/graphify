"""INC118: preceding same-TU anonymous helpers retain source-owned calls."""
from __future__ import annotations

import copy

import pytest

from graphify.extract import extract, extract_cpp
from graphify.extractors.cpp_free_calls import resolve_free_function_calls
from tests.cpp_same_unit_helpers import validate_span


def source(shape="ordinary"):
    helper = "namespace { void helper(){} }\n"
    body = "struct Panel{void run();};\nvoid Panel::run(){helper();}\n"
    if shape == "named":
        return "namespace Public {\n" + helper + body + "}\n"
    if shape == "reopened":
        return "namespace Public {" + helper + "}\nnamespace Public {" + body + "}\n"
    if shape == "multiple_blocks":
        return helper + "namespace {void different(){}}\n" + body
    if shape == "shadow":
        return helper + body.replace("void run();", "void helper();void run();")
    if shape == "local":
        return helper + body.replace("{helper();}", "{int helper=0;helper();}")
    if shape == "conditional":
        return "namespace {\n#if FLAG\nvoid helper(){}\n#endif\n}\n" + body
    if shape == "nested":
        return "namespace {" + helper + "}\n" + body
    if shape == "foreign_namespace":
        return "namespace Other {" + helper + "}\n" + body
    if shape == "conflict":
        return "void helper(){}\n" + helper + body
    if shape == "late":
        return "namespace {void helper();}\n" + body + helper
    if shape == "duplicate":
        return helper + helper + body
    return helper + body


def produce(root, raw, mode, *, foreign=False):
    """Both public extraction owners read real bytes and retain their own IDs."""
    path = root / "panel.cpp"
    path.write_bytes(raw)
    if foreign:
        (root / "other.cpp").write_bytes(b"namespace {void helper(){}}\n")
    if mode == "direct":
        return extract_cpp(path)
    paths = sorted(root.glob("*.cpp"))
    cold = extract(paths, root=root, cache_root=root, parallel=False)
    assert cold == extract(paths, root=root, cache_root=root, parallel=False)
    assert not cold.get("failed_sources")
    return cold


def helper_calls(result):
    targets = {node["id"] for node in result["nodes"] if node.get("label") == "helper()"}
    return [edge for edge in result["edges"] if edge.get("relation") == "calls" and edge.get("target") in targets]


@pytest.mark.parametrize("mode", ["direct", "facade"])
@pytest.mark.parametrize("shape", ["ordinary", "named", "reopened", "multiple_blocks"])
@pytest.mark.parametrize("newline", ["lf", "bom_crlf"])
def test_req_qml022_ac06_anonymous_helper_keeps_the_actual_member_body_call(tmp_path, mode, shape, newline):
    """Unique preceding helpers survive repaired member ownership and original byte offsets."""
    raw = source(shape).encode()
    if newline == "bom_crlf":
        raw = b"\xef\xbb\xbf// \xcf\x80\r\n" + raw.replace(b"\n", b"\r\n")
    result = produce(tmp_path, raw, mode)
    edge, = helper_calls(result)
    assert edge["confidence"] == "EXTRACTED" and edge["context"] == "cpp_free_function"
    target, = [node for node in result["nodes"] if node["id"] == edge["target"]]
    fact = target["metadata"]["cpp_function"]
    assert fact["namespace_status"] == "anonymous"
    proof = fact["anonymous_scope_proof"]
    assert proof["contract_version"] == 1 and proof["complete"] is True
    for scope in proof["scopes"]:
        validate_span(raw, scope)
    assert (tmp_path / "panel.cpp").read_bytes() == raw


@pytest.mark.parametrize("mode", ["direct", "facade"])
@pytest.mark.parametrize("shape", ["shadow", "local", "conditional", "nested", "foreign_namespace", "conflict", "late", "duplicate"])
def test_req_qml022_ac06_anonymous_helpers_do_not_borrow_unsupported_lookup(tmp_path, mode, shape):
    """A preceding source record is insufficient when visibility or uniqueness is unavailable."""
    assert not helper_calls(produce(tmp_path, source(shape).encode(), mode))


@pytest.mark.parametrize("mode", ["direct", "facade"])
def test_req_qml022_ac06_anonymous_helper_cannot_cross_translation_units(tmp_path, mode):
    """An external prototype never borrows another TU's anonymous implementation."""
    raw = b"void helper();\nstruct Panel{void run();};\nvoid Panel::run(){helper();}\n"
    assert not helper_calls(produce(tmp_path, raw, mode, foreign=True))


@pytest.mark.parametrize("damage", ["absent", "partial", "scope", "span", "version"])
def test_req_qml022_ac06_anonymous_scope_promise_is_not_positive_from_status_or_hash(tmp_path, damage):
    """Accepted producer data becomes unavailable when its original namespace witness is damaged."""
    result = produce(tmp_path, source().encode(), "direct")
    edge, = helper_calls(result)
    result = copy.deepcopy(result)
    result["edges"] = [item for item in result["edges"] if item.get("relation") != "calls"]
    node = next(item for item in result["nodes"] if item["id"] == edge["target"])
    fact = node["metadata"]["cpp_function"]
    if damage == "absent":
        fact.pop("anonymous_scope_proof")
    elif damage == "partial":
        fact["anonymous_scope_proof"]["complete"] = False
    elif damage == "scope":
        fact["anonymous_scope_proof"]["scopes"][0]["name_b64"] = "T3RoZXI="
    elif damage == "span":
        fact["anonymous_scope_proof"]["scopes"][0]["span"]["start_byte"] += 1
    else:
        fact["anonymous_scope_proof"]["contract_version"] = True
    # Reuse the genuine raw source-call transport, not a fabricated call site.
    resolve_free_function_calls(result["nodes"], result["edges"], result["raw_calls"])
    assert not helper_calls(result)
