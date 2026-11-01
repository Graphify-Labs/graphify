"""INC-QML-15: accepted constructor signatures retain independent source owners."""
from __future__ import annotations

import copy
import base64
import hashlib

import pytest

from graphify.extract import extract, extract_cpp
from graphify.extractors.cpp_constructors import bind_cpp_constructors


def constructors(result):
    """Select producer contracts rather than labels shared by every overload."""
    return [node for node in result["nodes"]
            if node.get("metadata", {}).get("cpp_constructor")]


def source_pair(root, declarations="Backend(); Backend(int value);", definitions=None, namespace=""):
    """Sibling files establish exact class ownership without executing constructors."""
    header = f"class Backend {{public: {declarations}}};"
    body = definitions or "Backend::Backend() {}\nBackend::Backend(int value) {}\n"
    if namespace:
        header = f"namespace {namespace} {{ {header} }}"
        body = body.replace("Backend::Backend", f"{namespace}::Backend::Backend")
    paths = [root / "backend.hpp", root / "backend.cpp"]
    for path, source in zip(paths, (header, '#include "backend.hpp"\n' + body)):
        path.write_bytes(source.encode())
    return paths


@pytest.mark.parametrize("namespace", ["", "Shared", "Shared::Inner"])
def test_req_qml008_ac02_overload_producer_ids_spans_and_exact_declaration_merge(tmp_path, namespace):
    """Each real definition and prototype owns its signature, line and canonical containment."""
    paths = source_pair(tmp_path, namespace=namespace)
    direct = [extract_cpp(path) for path in paths]
    assert [len(constructors(result)) for result in direct] == [2, 2]
    for path, result in zip(paths, direct):
        assert len({node["id"] for node in constructors(result)}) == 2
        for node in constructors(result):
            fact = node["metadata"]["cpp_constructor"]
            span = fact["span"]
            original = path.read_bytes()[span["start_byte"]:span["end_byte"]]
            assert b"Backend(" in original and node["source_location"] == f"L{span['start_row'] + 1}"
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    merged = constructors(result)
    assert len(merged) == 2
    assert {node["definition_location"] for node in merged} == {"L2", "L3"}
    owner = next(node for node in result["nodes"] if node.get("_callable_class"))
    assert all(any(edge["source"] == owner["id"] and edge["target"] == node["id"]
                   and edge["relation"] == "method" for edge in result["edges"]) for node in merged)


def test_req_qml008_ac03_inline_delegating_overloads_have_independent_fact_locations(tmp_path):
    """Delegation is a distinct constructor body; it does not select the delegated overload target."""
    path = tmp_path / "inline.cpp"
    path.write_bytes(b"class Backend {public:\n Backend() : Backend(0) {}\n Backend(int value) {}\n};")
    result = extract_cpp(path)
    found = constructors(result)
    assert len(found) == 2 and len({node["id"] for node in found}) == 2
    assert {node["source_location"] for node in found} == {"L2", "L3"}
    assert all(node["metadata"]["cpp_constructor"]["role"] == "definition" for node in found)


def test_req_qml008_ac02_corrupt_signature_never_binds_another_overload(tmp_path):
    """A forged signature copied from a sibling overload cannot acquire its source authority."""
    paths = source_pair(tmp_path)
    direct = [extract_cpp(path) for path in paths]
    nodes = copy.deepcopy([node for result in direct for node in result["nodes"]])
    edges = copy.deepcopy([edge for result in direct for edge in result["edges"]])
    definitions = [node for node in nodes if node.get("metadata", {}).get("cpp_constructor", {}).get("role") == "definition"]
    assert len(definitions) == 2
    definitions[0]["metadata"]["cpp_constructor"]["signature"] = definitions[1]["metadata"]["cpp_constructor"]["signature"]
    bind_cpp_constructors(nodes, edges)
    assert definitions[0]["metadata"]["cpp_constructor"].get("owner_bound") is not True


@pytest.mark.parametrize("declared,defined", [
    ("", "void"), ("int value = 0", "const int renamed"), ("unsigned", "unsigned int other"),
    ("const int &left", "int const &right"), ("int * const pointer", "int *other"),
    ("QObject *parent = nullptr", "QObject *renamed"), ("const Backend &copy", "Backend const &other"),
    ("int &&value", "int &&other"), ("unsigned long long", "long unsigned long number"),
])
def test_req_qml008_ac02_accepted_parameter_equivalence_joins_exact_original_spans(tmp_path, declared, defined):
    """Parameter names/defaults and value-only CV cannot split one real constructor signature."""
    paths = source_pair(tmp_path, f"Backend({declared});", f"Backend::Backend({defined}) {{}}")
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    found = constructors(result)
    assert len(found) == 1 and found[0]["definition_file"] == "backend.cpp"
    fact = found[0]["metadata"]["cpp_constructor"]
    span = fact["definition_span"]
    assert paths[1].read_bytes()[span["start_byte"]:span["end_byte"]] == f"Backend::Backend({defined}) {{}}".encode()


@pytest.mark.parametrize("parameters", [
    ("int value", "double value"), ("int *value", "const int *value"),
    ("int &value", "const int &value"), ("int &value", "int &&value"),
    ("int **value", "int *const *value"), ("signed char value", "unsigned char value"),
])
def test_req_qml008_ac02_distinct_pointer_reference_and_builtin_types_never_collapse(tmp_path, parameters):
    """Pointee CV, reference kind and builtin signedness are meaningful signature distinctions."""
    decl = " ".join(f"Backend({value});" for value in parameters)
    body = "\n".join(f"Backend::Backend({value}) {{}}" for value in parameters)
    result = extract(source_pair(tmp_path, decl, body), root=tmp_path, cache_root=tmp_path, parallel=False)
    assert len(constructors(result)) == 2 and len({node["id"] for node in constructors(result)}) == 2
    assert all(node.get("definition_file") == "backend.cpp" for node in constructors(result))


@pytest.mark.parametrize("parameter", ["Alias value", "std::vector<int> value", "void (*callback)(int)",
                                      "int array[3]", "...", "Unknown &value"])
def test_req_qml008_ac03_unsupported_signatures_keep_visible_distinct_occurrences_without_owner(tmp_path, parameter):
    """Insufficient type/alias authority cannot bind a convenient constructor prototype."""
    paths = source_pair(tmp_path, f"Backend({parameter});", f"Backend::Backend({parameter}) {{}}")
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    found = constructors(result)
    assert len(found) == 2
    definition = next(node for node in found if node["source_file"] == "backend.cpp")
    assert definition["metadata"]["cpp_constructor"]["ambiguous"] is True
    assert not any(edge["target"] == definition["id"] and edge["relation"] == "method" for edge in result["edges"])


@pytest.mark.parametrize("corrupt", ["signature_b64", "signature", "signature_and_transport", "scope", "id", "span", "inline_parent"])
def test_req_qml008_ac03_direct_binding_rejects_corrupted_identity_transport(tmp_path, corrupt):
    """Source contracts, salted identity and real class containment must agree at the direct join."""
    paths = source_pair(tmp_path)
    direct = [extract_cpp(path) for path in paths]
    nodes = copy.deepcopy([node for result in direct for node in result["nodes"]])
    edges = copy.deepcopy([edge for result in direct for edge in result["edges"]])
    definition = next(node for node in nodes if node.get("metadata", {}).get("cpp_constructor", {}).get("role") == "definition")
    fact = definition["metadata"]["cpp_constructor"]
    if corrupt == "signature_b64":
        fact["signature_b64"] = "invalid!"
    elif corrupt == "signature":
        fact["signature"] = "0" * 64
    elif corrupt == "signature_and_transport":
        fact["signature_b64"] = base64.b64encode(b"ctor2\0double").decode()
        fact["signature"] = hashlib.sha256(b"ctor2\0double").hexdigest()
    elif corrupt == "scope":
        fact["scope_b64"] = base64.b64encode(b"Wrong").decode()
    elif corrupt == "id":
        definition["id"] = "impostor_cppctor_" + fact["signature"]
    elif corrupt == "span":
        fact["span"]["start_row"] += 1
    else:
        fact["owner_bound"] = True
        edges.append({"source": "foreign", "target": definition["id"], "relation": "method",
                      "confidence": "EXTRACTED", "source_file": definition["source_file"],
                      "source_location": definition["source_location"]})
    bind_cpp_constructors(nodes, edges)
    assert fact.get("owner_bound") is not True


def test_req_qml008_ac02_constructor_ids_survive_overload_addition_removal_and_parameter_rename(tmp_path):
    """Signature identity is independent of overload cardinality and neighboring source positions."""
    paths = source_pair(tmp_path, "Backend(int value);", "Backend::Backend(int value) {}")
    first = next(node for node in constructors(extract_cpp(paths[1])))
    paths = source_pair(tmp_path, "Backend(); Backend(int other);", "Backend::Backend() {}\nBackend::Backend(int renamed) {}")
    later = next(node for node in constructors(extract_cpp(paths[1]))
                 if node["metadata"]["cpp_constructor"]["signature"] == first["metadata"]["cpp_constructor"]["signature"])
    assert later["id"] == first["id"]


def test_req_qml008_ac02_constructor_and_unrelated_method_ids_keep_independent_generic_calls(tmp_path):
    """Every body owns its helper call; non-constructor function/member IDs retain upstream identity."""
    paths = source_pair(tmp_path, "Backend(); Backend(int); int work();",
                        "int helper(){return 1;}\nBackend::Backend() {helper();}\nBackend::Backend(int value) {helper();}\nint Backend::work(){return helper();}")
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    helper = next(node for node in result["nodes"] if node["label"] == "helper()")
    method = next(node for node in result["nodes"] if node["label"] == ".work()")
    assert method["id"] == "backend_backend_work"
    assert all(any(edge["source"] == node["id"] and edge["target"] == helper["id"] and edge["relation"] == "calls"
                   for edge in result["edges"]) for node in constructors(result) + [method])


@pytest.mark.parametrize("count", [51, 64])
def test_req_qml008_ac02_signature_authority_keeps_arguments_beyond_display_list_limit(tmp_path, count):
    """A differing last parameter must survive the graph's fifty-item display bound."""
    shared = [f"int value{index}" for index in range(count - 1)]
    parameters = [", ".join(shared + ["int final"]), ", ".join(shared + ["double final"])]
    paths = source_pair(tmp_path, " ".join(f"Backend({value});" for value in parameters),
                        "\n".join(f"Backend::Backend({value}) {{}}" for value in parameters))
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    found = constructors(result)
    assert len(found) == 2 and len({node["id"] for node in found}) == 2
    assert all(node.get("definition_file") == "backend.cpp" for node in found)


def test_req_qml008_ac03_parameter_overflow_cannot_turn_prefix_into_accepted_signature(tmp_path):
    """Sixty-five parameters retain source occurrences while refusing truncated type proof."""
    parameter = ", ".join(f"int value{index}" for index in range(65))
    result = extract(source_pair(tmp_path, f"Backend({parameter});", f"Backend::Backend({parameter}) {{}}"),
                     root=tmp_path, cache_root=tmp_path, parallel=False)
    assert len(constructors(result)) == 2
    assert all(node["metadata"]["cpp_constructor"]["ambiguous"] for node in constructors(result))


@pytest.mark.parametrize("qualifier", ["const", "volatile", "const volatile"])
def test_req_qml008_ac03_qualified_void_cannot_authorize_zero_argument_constructor(tmp_path, qualifier):
    """Only sole unnamed unqualified void represents an empty parameter list."""
    paths = source_pair(tmp_path, "Backend();", f"Backend::Backend({qualifier} void) {{}}")
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not any(node.get("definition_file") for node in constructors(result))
