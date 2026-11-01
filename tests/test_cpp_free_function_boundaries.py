"""INC-QML-73: rooted lookup and transported source proof fail closed."""
from __future__ import annotations

import base64
from copy import deepcopy

import pytest

from graphify.extract import extract, extract_cpp
from graphify.extractors.cpp_free_calls import resolve_free_function_calls
from graphify.extractors.cpp_functions import free_definition_fact


def _name(node):
    return base64.b64decode(node["metadata"]["cpp_function"]["qualified_name_b64"]).decode()


def test_req_qml022_ac06_global_qualification_bypasses_enclosing_namespace(tmp_path):
    """A source `::` fixes the lookup root even when the enclosing namespace has a homonym."""
    path = tmp_path / "api.cpp"
    path.write_text("int work(int value){return value;} namespace First {"
                    "int work(int value){return value;} int caller(){return ::work(1);}}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    nodes = {node["id"]: node for node in result["nodes"] if free_definition_fact(node)}
    caller = next(key for key, node in nodes.items() if _name(node) == "First::caller")
    targets = {_name(nodes[edge["target"]]) for edge in result["edges"]
               if edge["source"] == caller and edge["relation"] == "calls" and edge["target"] in nodes}
    assert targets == {"work"}


@pytest.mark.parametrize("reverse", [False, True])
def test_req_qml022_ac02_alias_and_free_definition_keep_separate_roles(tmp_path, reverse):
    """Case-folded ordinary IDs cannot attach a function proof to a preceding type alias."""
    path = tmp_path / "api.cpp"
    declarations = ["using Callback=void(*)();", "void callback(){}"]
    path.write_text("\n".join(reversed(declarations) if reverse else declarations))
    result = extract_cpp(path)
    assert len([node for node in result["nodes"] if node["label"] == "Callback"]) == 1
    bodies = [node for node in result["nodes"] if free_definition_fact(node)]
    assert len(bodies) == 1 and bodies[0]["label"] == "callback()"
    assert bodies[0]["source_location"] == ("L1" if reverse else "L2")


@pytest.mark.parametrize("mutation", ["namespace", "scope", "span", "fingerprint", "complete", "proof_type"])
def test_req_qml022_ac06_definition_transport_rejects_corrupt_namespace_proof(tmp_path, mutation):
    """A transported convenience name cannot replace the original namespace witness or identity."""
    path = tmp_path / "api.cpp"
    path.write_text("namespace First { int work(int value){return value;} }")
    node = deepcopy(next(node for node in extract_cpp(path)["nodes"] if free_definition_fact(node)))
    fact = node["metadata"]["cpp_function"]
    if mutation == "namespace":
        fact["namespace_b64"] = base64.b64encode(b"Other").decode()
        fact["qualified_name_b64"] = base64.b64encode(b"Other::work").decode()
    elif mutation == "scope":
        fact["namespace_proof"][0]["name_b64"] = base64.b64encode(b"Other").decode()
    elif mutation == "span":
        fact["namespace_proof"][0]["span"]["end_byte"] = fact["span"]["start_byte"]
    elif mutation == "fingerprint":
        fact["scope_fingerprint"] = "0" * 64
    elif mutation == "complete":
        fact["scope_complete"] = []
    else:
        fact["namespace_proof"] = True
    assert free_definition_fact(node) == {}


@pytest.mark.parametrize("key,value", [("min_args", True), ("max_args", "1"),
    ("canonical_parameters", True), ("canonical_status", "bogus"), ("signature_status", "bogus")])
def test_req_qml022_ac06_corrupt_prototype_transport_cannot_authorize_default_call(tmp_path, key, value):
    """Malformed cached declarations neither crash the production resolver nor lend a default arity."""
    path = tmp_path / "api.cpp"
    path.write_text("int work(int value=1); int work(int value){return value;} int caller(){return work();}")
    result = extract_cpp(path)
    nodes = deepcopy(result["nodes"])
    prototype = next(node for node in nodes if "cpp_prototype" in node.get("metadata", {}))
    prototype["metadata"]["cpp_prototype"][key] = value
    edges = [edge for edge in deepcopy(result["edges"]) if edge["relation"] != "calls"]
    raw_calls = deepcopy(result.get("raw_calls", []))
    resolve_free_function_calls(nodes, edges, raw_calls)
    assert not any(edge["relation"] == "calls" for edge in edges)


@pytest.mark.parametrize("declaration", ["#if FEATURE\nint work(int value=1);\n#endif\n",
    "template<class T> int work(int value=1);\n"])
def test_req_qml022_ac06_conditional_or_template_defaults_cannot_lend_body_arity(tmp_path, declaration):
    """An unavailable branch or non-deducible template cannot make an ordinary body callable with zero arguments."""
    path = tmp_path / "api.cpp"
    path.write_text(declaration + "int work(int value){return value;} int caller(){return work();}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not any(edge["relation"] == "calls" for edge in result["edges"])


def test_req_qml022_ac06_unprovided_header_default_does_not_change_caller_arity(tmp_path):
    """The complete graph is not proof that an unrelated declaration is visible at a call site."""
    values = {"api.hpp": "int work(int value=1);", "api.cpp": "int work(int value){return value;}",
              "caller.cpp": "int caller(){return work();}"}
    for name, source in values.items():
        (tmp_path / name).write_text(source)
    result = extract([tmp_path / name for name in values], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not any(edge["relation"] == "calls" for edge in result["edges"])


@pytest.mark.parametrize("binding", ["int callback;", "int (*callback)();"])
def test_req_qml022_ac06_rooted_function_bypasses_class_field_shadow(tmp_path, binding):
    """An explicit global function name bypasses class storage with the same spelling."""
    path = tmp_path / "api.cpp"
    path.write_text("int callback(){return 1;} class Checks{public:" + binding
                    + "int run(){return ::callback();}};")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    body = next(node for node in result["nodes"] if free_definition_fact(node))
    caller = next(node for node in result["nodes"] if node["label"].removeprefix(".") == "run()")
    assert any(edge["relation"] == "calls" and edge["source"] == caller["id"] and edge["target"] == body["id"]
               for edge in result["edges"])


@pytest.mark.parametrize("key", ["signature_status", "namespace_status", "canonical_status"])
@pytest.mark.parametrize("value", [[], {}, True])
def test_req_qml022_ac06_malformed_status_values_reject_without_hashing_failure(tmp_path, key, value):
    """Malformed cache transport is unavailable proof, not a producer/resolver crash."""
    path = tmp_path / "api.cpp"
    path.write_text("int work(){return 1;}")
    node = deepcopy(next(node for node in extract_cpp(path)["nodes"] if free_definition_fact(node)))
    node["metadata"]["cpp_function"][key] = value
    assert free_definition_fact(node) == {}


def test_req_qml022_ac02_free_function_collision_with_its_file_node_retains_proof(tmp_path):
    """The shared declaration allocator's file reservation cannot invalidate a genuine body."""
    path = tmp_path / "api.cpp"
    path.write_text("int cpp(){return 1;} int caller(){return cpp();}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    bodies = {node["id"]: node for node in result["nodes"] if free_definition_fact(node)}
    target = next(identity for identity, node in bodies.items() if _name(node) == "cpp")
    caller = next(identity for identity, node in bodies.items() if _name(node) == "caller")
    assert target != "api_cpp"
    assert any(edge["source"] == caller and edge["target"] == target and edge["relation"] == "calls" for edge in result["edges"])


def test_req_qml022_ac06_large_namespace_scope_uses_bounded_keys_without_lookup_authority(tmp_path):
    """Very deep source scope remains an exact declaration identity with explicit unavailable lookup."""
    from graphify.extractors.cpp_functions import bounded_scope
    parts = ["Scope" + str(index) for index in range(80)]
    key, fingerprint = bounded_scope(parts)
    assert len(key) < 80 and len(fingerprint) == 64
    path = tmp_path / "api.cpp"
    path.write_text("".join("namespace " + part + "{" for part in parts)
                    + "int work(){return 1;} int caller(){return work();}" + "}" * len(parts))
    result = extract_cpp(path)
    facts = [node["metadata"]["cpp_function"] for node in result["nodes"] if "cpp_function" in node.get("metadata", {})]
    assert len(facts) == 2 and all(fact["namespace_status"] == "oversize" for fact in facts)
    assert all(fact["scope_complete"] is False and not fact["qualified_name_b64"] for fact in facts)
    assert all(len(fact["namespace_proof"]) <= 50 for fact in facts)
    assert not any(edge["relation"] == "calls" for edge in result["edges"])


@pytest.mark.parametrize("family,field,value", [
    ("cpp_function", "signature_status", []), ("cpp_function", "namespace_status", {}),
    ("cpp_function", "scope_complete", []), ("cpp_prototype", "min_args", True),
    ("cpp_prototype", "max_args", "1"), ("cpp_prototype", "canonical_parameters", True),
    ("cpp_prototype", "qualified_name_b64", []),
])
def test_req_qml022_ac06_facade_borrowed_transport_rejects_corruption_without_source_discovery(tmp_path, family, field, value):
    """The real facade must not crash or use corrupted persisted context as call authority."""
    owner = tmp_path / "api.cpp"
    owner.write_text("int work(int value=1); int work(int value){return value;}")
    original = extract_cpp(owner)
    borrowed = deepcopy([node for node in original["nodes"] if family in node.get("metadata", {})])
    assert len(borrowed) == 1
    borrowed[0]["metadata"][family][field] = value
    caller = tmp_path / "caller.cpp"
    caller.write_text("int caller(){return work();}")
    # The borrowed source is deliberately unavailable: no fallback may open it.
    owner.unlink()
    result = extract([caller], root=tmp_path, cache_root=tmp_path, parallel=False,
                     resolution_context_nodes=borrowed, resolution_context_edges=[])
    assert not result["failed_sources"] and not result["qml_failures"]
    assert not any(edge["relation"] == "calls" for edge in result["edges"])


@pytest.mark.parametrize("source", [
    "#if FEATURE\nint work(int value){return value;}\n#endif\nint caller(){return work(1);}",
    "int work(auto value){return 1;} int caller(){return work(1);}",
    "int work(int value,...){return value;} int caller(){return work(1,2);}",
])
def test_req_qml022_ac06_unavailable_definition_contracts_do_not_choose_concrete_bodies(tmp_path, source):
    """Conditional, abbreviated-template and variadic definitions remain explicit uncertainty."""
    path = tmp_path / "api.cpp"
    path.write_text(source)
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert len([node for node in result["nodes"] if "cpp_function" in node.get("metadata", {})]) == 2
    assert not any(edge["relation"] == "calls" for edge in result["edges"])


def test_req_qml022_ac02_conditional_definition_occurrences_do_not_collapse(tmp_path):
    """Each branch owns its own source span even when both definitions have the same signature."""
    path = tmp_path / "api.cpp"
    path.write_text("#if FEATURE\nint work(int value){return value;}\n#else\n"
                    "int work(int value){return value+1;}\n#endif\nint caller(){return work(1);}")
    result = extract_cpp(path)
    bodies = [node for node in result["nodes"] if node["label"] == "work()"]
    assert len(bodies) == len({node["id"] for node in bodies}) == 2
    assert {node["source_location"] for node in bodies} == {"L2", "L4"}
    assert all(free_definition_fact(node).get("ambiguous") is True for node in bodies)
    assert not any(edge["relation"] == "calls" for edge in result["edges"])


def test_req_qml022_ac06_redeclared_same_file_default_retains_each_prototype(tmp_path):
    """The later visible default cannot disappear behind the first declaration's shared signature."""
    path = tmp_path / "api.cpp"
    path.write_text("int work(int value);\nint work(int value=1);\n"
                    "int work(int value){return value;}\nint caller(){return work();}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    declarations = [node for node in result["nodes"] if "cpp_prototype" in node.get("metadata", {})]
    assert len(declarations) == len({node["id"] for node in declarations}) == 2
    assert {node["source_location"] for node in declarations} == {"L1", "L2"}
    bodies = {node["id"]: node for node in result["nodes"] if free_definition_fact(node)}
    assert any(edge["relation"] == "calls" and bodies.get(edge["target"], {}).get("label") == "work()"
               for edge in result["edges"])


@pytest.mark.parametrize("source,expected", [
    ("int work(int value=1){return value;} int caller(){return work();}", True),
    ("int work(int value); int caller(){return work();} int work(int value=1){return value;}", False),
    ("int work(int value); int caller(){return work();} int work(int value=1); int work(int value){return value;}", False),
    ("int work(int value); int caller(){return work(1);} int work(int value=1){return value;}", True),
])
def test_req_qml022_ac06_default_arity_requires_forward_source_visibility(tmp_path, source, expected):
    """A later default cannot retroactively make an earlier source call well formed."""
    path = tmp_path / "api.cpp"
    path.write_text(source)
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert any(edge["relation"] == "calls" for edge in result["edges"]) is expected


def test_req_qml022_ac06_namespace_free_call_cannot_also_bind_foreign_homonym_class(tmp_path):
    """A receiver-typed fallback cannot borrow an unrelated class matching a source namespace."""
    path = tmp_path / "api.cpp"
    path.write_text("namespace First{int work(int value){return value;}}"
                    "namespace Other{class First{public:static int work(int value){return value;}};}"
                    "int caller(){return First::work(1);}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    caller = next(node for node in result["nodes"] if node["label"] == "caller()")
    by_id = {node["id"]: node for node in result["nodes"]}
    targets = [by_id[edge["target"]] for edge in result["edges"] if edge["source"] == caller["id"] and edge["relation"] == "calls"]
    assert len(targets) == 1 and free_definition_fact(targets[0])
    assert _name(targets[0]) == "First::work"
