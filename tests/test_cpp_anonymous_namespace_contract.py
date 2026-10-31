"""INC118: bounded original namespace witnesses survive public consumers."""
from __future__ import annotations

import copy

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.cpp_anonymous_namespaces import anonymous_namespace
from graphify.extractors.cpp_free_calls import resolve_free_function_calls
from graphify.paths import load_node_link_graph
from graphify.source_relationships import logical_endpoints
from tests.test_cpp_anonymous_helper_calls import helper_calls, produce, source


@pytest.mark.parametrize("mode", ["direct", "facade"])
@pytest.mark.parametrize("caller", ["free", "constructor", "nested_class", "nested_namespace"])
def test_req_qml022_ac06_anonymous_lookup_preserves_existing_caller_roles(tmp_path, mode, caller):
    """Actual source-owned callers retain their IDs; the namespace record creates no new callable."""
    bodies = {
        "free": "void caller(){helper();}",
        "constructor": "struct Panel{Panel(){helper();}};",
        "nested_class": "struct Outer{struct Inner{void run(){helper();}};};",
        "nested_namespace": "namespace Child{struct Panel{void run(){helper();}};}",
    }
    raw = ("namespace Public { namespace{void helper(){}}\n" + bodies[caller] + "}\n").encode()
    result = produce(tmp_path, raw, mode)
    edge, = helper_calls(result)
    assert edge["context"] == "cpp_free_function"
    assert any(node["id"] == edge["source"] and node.get("_callable") for node in result["nodes"])


@pytest.mark.parametrize("mode", ["direct", "facade"])
def test_req_qml022_ac06_anonymous_scope_survives_assembly_sanitation_export_and_path_reload(tmp_path, mode):
    """Public storage preserves every source role/span without interpreting proof as a namespace node."""
    result = produce(tmp_path, source("reopened").encode(), mode)
    edge, = helper_calls(result)
    target = next(node for node in result["nodes"] if node["id"] == edge["target"])
    expected = copy.deepcopy(target["metadata"]["cpp_function"]["anonymous_scope_proof"])
    graph = build_from_json(result, root=tmp_path, directed=True)
    path = tmp_path / "saved.json"
    assert to_json(graph, {}, str(path))
    restored = load_node_link_graph(path)
    assert restored.nodes[edge["target"]]["metadata"]["cpp_function"]["anonymous_scope_proof"] == expected
    assert any(data.get("relation") == "calls" and logical_endpoints(restored, left, right, data) == (edge["source"], edge["target"])
               for left, right, data in restored.edges(data=True))


@pytest.mark.parametrize("scopes,accepted", [(50, True), (51, False)])
def test_req_qml022_ac06_anonymous_scope_bounds_never_truncate_positive_authority(tmp_path, scopes, accepted):
    """The complete source-role list fits the50-item sanitizer bound or explicitly declines lookup."""
    wrappers = "".join(f"namespace N{i}{{" for i in range(scopes - 1))
    raw = (wrappers + source() + "}" * (scopes - 1)).encode()
    result = produce(tmp_path, raw, "direct")
    assert bool(helper_calls(result)) is accepted
    fact = next(node["metadata"]["cpp_function"] for node in result["nodes"] if node.get("label") == "helper()")
    witness = fact["anonymous_scope_proof"]
    assert witness["complete"] is accepted and len(witness["scopes"]) == (50 if accepted else 0)


@pytest.mark.parametrize("key,value", [
    ("contract_version", []), ("complete", 1), ("scopes", None),
    ("kind", []), ("name_b64", []), ("span", []),
])
def test_req_qml022_ac06_malformed_anonymous_witness_is_controlled_unavailable(tmp_path, key, value):
    """Damaged source transport never reaches hashing or becomes a convenient named target."""
    result = produce(tmp_path, source().encode(), "direct")
    edge, = helper_calls(result)
    node = copy.deepcopy(next(node for node in result["nodes"] if node["id"] == edge["target"]))
    fact = node["metadata"]["cpp_function"]
    witness = fact["anonymous_scope_proof"]
    if key in {"kind", "name_b64", "span"}:
        witness["scopes"][0][key] = value
    else:
        witness[key] = value
    assert anonymous_namespace(node, fact) is None


@pytest.mark.parametrize("damage", ["absent", "inferred", "foreign"])
def test_req_qml022_ac06_anonymous_target_needs_its_actual_extracted_file_containment(tmp_path, damage):
    """Node path text cannot replace the accepted target's independent original file edge."""
    result = produce(tmp_path, source().encode(), "direct")
    edge, = helper_calls(result)
    result = copy.deepcopy(result)
    result["edges"] = [item for item in result["edges"] if item.get("relation") != "calls"]
    contains = next(item for item in result["edges"] if item.get("relation") == "contains" and item.get("target") == edge["target"])
    if damage == "absent":
        result["edges"].remove(contains)
    elif damage == "inferred":
        contains["confidence"] = "INFERRED"
    else:
        contains["source_file"] = "foreign.cpp"
    resolve_free_function_calls(result["nodes"], result["edges"], result["raw_calls"])
    assert not helper_calls(result)


@pytest.mark.parametrize("mode", ["direct", "facade"])
@pytest.mark.parametrize("arguments,accepted", [("", True), ("1,2", False)])
def test_req_qml022_ac06_anonymous_candidates_keep_existing_original_arity_limits(tmp_path, mode, arguments, accepted):
    """Same-TU visibility preserves source defaults without bypassing the existing callable arity proof."""
    raw = source().replace("void helper(){}", "void helper(int value=0){}").replace("{helper();}", "{helper(" + arguments + ");}").encode()
    assert bool(helper_calls(produce(tmp_path, raw, mode))) is accepted


@pytest.mark.parametrize("mode", ["direct", "facade"])
@pytest.mark.parametrize("foreign", [
    "namespace Other{namespace{namespace{void helper(){}}}}",
    "namespace{namespace Other{namespace{void helper(){}}}}",
])
def test_req_qml022_ac06_foreign_nested_anonymous_names_do_not_veto_a_named_call(tmp_path, mode, foreign):
    """Unsupported anonymous lookup is scoped negative evidence, never a TU-wide name ban."""
    raw = (foreign + "\nvoid helper(){}\nstruct Panel{void run();};void Panel::run(){helper();}\n").encode()
    result = produce(tmp_path, raw, mode)
    edge, = helper_calls(result)
    target = next(node for node in result["nodes"] if node["id"] == edge["target"])
    assert target["metadata"]["cpp_function"]["namespace_status"] == "available"


@pytest.mark.parametrize("mode", ["direct", "facade"])
def test_req_qml022_ac06_same_host_unknown_anonymous_lookup_stops_outer_fallback(tmp_path, mode):
    """A nearer source-owned unsupported candidate cannot fall through to a convenient global helper."""
    raw = ("void helper(){}\nnamespace Public{namespace{namespace{void helper(){}}}"
           "struct Panel{void run();};void Panel::run(){helper();}}\n").encode()
    assert not helper_calls(produce(tmp_path, raw, mode))


@pytest.mark.parametrize("mode", ["direct", "facade"])
def test_req_qml022_ac06_later_unknown_anonymous_definition_does_not_hide_a_preceding_named_call(tmp_path, mode):
    """The rejection-only witness obeys the same original declaration order as positive helpers."""
    raw = ("void helper(){}\nstruct Panel{void run();};void Panel::run(){helper();}\n"
           "namespace{namespace{void helper(){}}}\n").encode()
    edge, = helper_calls(produce(tmp_path, raw, mode))
    assert edge["context"] == "cpp_free_function"


@pytest.mark.parametrize("mode", ["direct", "facade"])
def test_req_qml022_ac06_preceding_anonymous_prototype_blocks_a_competing_named_helper(tmp_path, mode):
    """A prior declaration is visible even when its unavailable implementation follows the call."""
    raw = ("void helper(){}\nnamespace{void helper();}\n"
           "struct Panel{void run();};void Panel::run(){helper();}\n"
           "namespace{void helper(){}}\n").encode()
    assert not helper_calls(produce(tmp_path, raw, mode))


@pytest.mark.parametrize("mode", ["direct", "facade"])
@pytest.mark.parametrize("declarations", [
    "namespace{void helper();void helper(){}}",
    "namespace{void helper();}namespace{void helper(){}}",
    "namespace Other{namespace{void helper();}}\nvoid helper(){}",
    "namespace{namespace Other{namespace{void helper();}}}\nvoid helper(){}",
])
def test_req_qml022_ac06_compatible_or_foreign_anonymous_declarations_preserve_existing_body(tmp_path, mode, declarations):
    """Canonical same-entity declarations or foreign-host uncertainty cannot erase a proven body call."""
    raw = (declarations + "\nstruct Panel{void run();};void Panel::run(){helper();}\n").encode()
    edge, = helper_calls(produce(tmp_path, raw, mode))
    assert edge["context"] == "cpp_free_function"


@pytest.mark.parametrize("mode", ["direct", "facade"])
def test_req_qml022_ac06_later_anonymous_prototype_does_not_retroactively_shadow(tmp_path, mode):
    """Rejection-only prototypes obey their actual source declaration order."""
    raw = ("void helper(){}\nstruct Panel{void run();};void Panel::run(){helper();}\n"
           "namespace{void helper();}\n").encode()
    assert len(helper_calls(produce(tmp_path, raw, mode))) == 1


@pytest.mark.parametrize("mode", ["direct", "facade"])
def test_req_qml022_ac06_anonymous_declaration_never_supplies_defaults_or_a_target(tmp_path, mode):
    """A declaration may prevent wrong fallback but cannot lend positive default-argument authority."""
    raw = ("namespace{void helper(int=0);void helper(int value){}}\n"
           "struct Panel{void run();};void Panel::run(){helper();}\n").encode()
    assert not helper_calls(produce(tmp_path, raw, mode))


@pytest.mark.parametrize("mode", ["direct", "facade"])
@pytest.mark.parametrize("declaration", ["void helper(){}", "void helper();"])
def test_req_qml022_ac06_same_named_namespace_inside_anonymous_scope_is_not_the_public_host(tmp_path, mode, declaration):
    """Named display paths cannot erase an intervening original anonymous namespace identity."""
    raw = ("namespace Public{void helper(){}}\n"
           "namespace{namespace Public{namespace{" + declaration + "}}}\n"
           "namespace Public{struct Panel{void run();};void Panel::run(){helper();}}\n").encode()
    result = produce(tmp_path, raw, mode)
    edge, = helper_calls(result)
    target = next(node for node in result["nodes"] if node["id"] == edge["target"])
    assert target["metadata"]["cpp_function"]["namespace_status"] == "available"
