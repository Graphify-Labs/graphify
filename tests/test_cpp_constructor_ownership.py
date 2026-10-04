"""REQ-QML-008-AC02: generic constructor facts retain proven class ownership."""
import copy
import base64

import pytest

from graphify.extract import extract, extract_cpp
from graphify.extractors.base import _file_stem, _make_id
from graphify.extractors.cpp_constructors import bind_cpp_constructors, constructor_merge_allowed


def corpus(root, header, implementation):
    """Use the real generic producer and aggregate with explicit corpus ownership."""
    paths = [root / "backend.hpp", root / "backend.cpp"]
    for path, source in zip(paths, (header, '#include "backend.hpp"\n' + implementation)):
        path.write_text(source, encoding="utf-8", newline="")
    return paths


def owner_edges(result, constructor):
    return [edge for edge in result["edges"] if edge["target"] == constructor["id"]
            and edge["relation"] == "method" and edge["confidence"] == "EXTRACTED"]


@pytest.mark.parametrize("prototype,definition", [
    ("Backend();", "Backend::Backend() : value(0) {}"),
    ("explicit Backend(int initial = 0);", "Backend::Backend(int initial) : value(initial) {}"),
])
def test_req_qml008_ac02_constructor_prototypes_are_callable_methods(tmp_path, prototype, definition):
    """Header declaration nodes are missing before the correction, unlike ordinary methods."""
    paths = corpus(tmp_path, f"class Backend {{public: {prototype} int value;}};", definition)
    direct = extract_cpp(paths[0])
    constructors = [node for node in direct["nodes"] if node.get("label") == ".Backend()"]
    assert len(constructors) == 1 and constructors[0].get("_callable") is True
    owners = owner_edges(direct, constructors[0])
    assert len(owners) == 1
    assert next(node for node in direct["nodes"] if node["id"] == owners[0]["source"])["label"] == "Backend"


@pytest.mark.parametrize("namespace,qualification", [
    ("", "Backend::Backend"),
    ("Shared", "Shared::Backend::Backend"),
    ("Shared", "namespace Shared { Backend::Backend"),
])
def test_req_qml008_ac02_constructor_definition_retains_id_and_exact_accepted_owner(tmp_path, namespace, qualification):
    """Explicit scope and header declarations authorize ownership without rewriting a definition ID."""
    header = "class Backend {public: explicit Backend(int initial); int value;};"
    if namespace:
        header = f"namespace {namespace} {{ {header} }}"
    implementation = qualification + "(int initial) : value(initial) {}"
    if qualification.startswith("namespace"):
        implementation += " }"
    paths = corpus(tmp_path, header, implementation)
    direct = extract_cpp(paths[1])
    definition = next(node for node in direct["nodes"] if node.get("_callable") and not node.get("_callable_class"))
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    constructors = [node for node in result["nodes"] if node.get("_callable") and "Backend" in node["label"]
                    and not node.get("_callable_class")]
    candidate = next(node for node in constructors if node.get("definition_file") == "backend.cpp"
                     or node.get("source_file") == "backend.cpp")
    assert candidate["id"] == "backend_" + definition["id"].removeprefix(_make_id(_file_stem(paths[1])) + "_")
    owners = owner_edges(result, candidate)
    assert len({edge["source"] for edge in owners}) == 1
    owner = next(node for node in result["nodes"] if node["id"] == owners[0]["source"])
    assert owner.get("_callable_class") is True and owner["source_file"] == "backend.hpp"


@pytest.mark.parametrize("header,implementation", [
    ("class Backend {public: Backend(double value);};", "Backend::Backend(int value) {}"),
    ("class Backend;", "Backend::Backend(int value) {}"),
    ("namespace Other {class Backend {public: Backend(int value);};}", "Foreign::Backend::Backend(int value) {}"),
    ("class Backend {public: Backend(int value); Backend(const int other);};", "Backend::Backend(int value) {}"),
    ("class Backend {public: Backend(...);};", "Backend::Backend() {}"),
    ("class Backend {public: Backend(unsigned int value);};", "Backend::Backend(unsignedint value) {}"),
])
def test_req_qml008_ac02_constructor_ownership_requires_complete_matching_unambiguous_proof(tmp_path, header, implementation):
    """Wrong signatures, incomplete classes, foreign scopes and duplicate signatures cannot invent an owner."""
    paths = corpus(tmp_path, header, implementation)
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    definition = next(node for node in result["nodes"] if node.get("_callable")
                      and (node.get("source_file") == "backend.cpp" or node.get("definition_file") == "backend.cpp"))
    assert not owner_edges(result, definition)


def test_req_qml008_ac02_constructor_binding_keeps_unrelated_generic_edges(tmp_path):
    """An ownership correction must preserve the producer's existing ID and field references."""
    paths = corpus(tmp_path, "class Backend {public: Backend(int initial); int value;};",
                   "int helper(){return 1;} Backend::Backend(int initial) : value(initial) {value=helper();}")
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    functions = {node["label"]: node for node in result["nodes"] if node.get("_callable") and not node.get("_callable_class")}
    constructor = next(node for node in functions.values() if "Backend" in node["label"])
    assert any(edge["source"] == constructor["id"] and edge["target"] == functions["helper()"]["id"]
               and edge["relation"] == "calls" for edge in result["edges"])
    before = copy.deepcopy(result)
    repeated = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert repeated == before


@pytest.mark.parametrize("corruption", ["wrong_line", "foreign_header", "inferred_parent", "conflicting_parent", "corrupt_transport", "foreign_edge", "wrong_edge_line", "corrupt_span", "not_callable", "reversed_columns", "conflicting_contains"])
def test_req_qml008_ac02_constructor_join_rejects_foreign_or_corrupt_accepted_proof(tmp_path, corruption):
    """Neither lexical names nor a collision replace exact source and extracted-parent authority."""
    paths = corpus(tmp_path, "class Backend {public: Backend(int initial);};", "Backend::Backend(int initial) {}")
    header, implementation = (extract_cpp(path) for path in paths)
    nodes = copy.deepcopy(header["nodes"] + implementation["nodes"])
    edges = copy.deepcopy(header["edges"] + implementation["edges"])
    definition = next(node for node in nodes if node.get("metadata", {}).get("cpp_constructor", {}).get("role") == "definition")
    prototype = next(node for node in nodes if node.get("metadata", {}).get("cpp_constructor", {}).get("role") == "declaration")
    if corruption == "wrong_line":
        definition["source_location"] = "L99"
    elif corruption == "foreign_header":
        prototype["source_file"] = "foreign.hpp"
    elif corruption == "inferred_parent":
        for edge in edges:
            if edge.get("relation") == "method":
                edge["confidence"] = "INFERRED"
    elif corruption == "conflicting_parent":
        edges.append({"source": "foreign_class", "target": definition["id"], "relation": "method", "confidence": "EXTRACTED"})
    elif corruption in {"foreign_edge", "wrong_edge_line"}:
        for edge in edges:
            if edge.get("relation") == "method":
                edge["source_file" if corruption == "foreign_edge" else "source_location"] = "foreign.hpp" if corruption == "foreign_edge" else "L99"
    elif corruption == "corrupt_span":
        definition["metadata"]["cpp_constructor"]["span"]["start_row"] = True
    elif corruption == "not_callable":
        definition["_callable"] = False
    elif corruption == "reversed_columns":
        definition["metadata"]["cpp_constructor"]["span"].update(start_column=5, end_column=0)
    elif corruption == "conflicting_contains":
        other_path = tmp_path / "other.hpp"
        other_path.write_text("class Other {};", encoding="utf-8")
        other = next(node for node in extract_cpp(other_path)["nodes"] if node.get("_callable_class"))
        nodes.append(other)
        edges.append({"source": other["id"], "target": definition["id"], "relation": "contains",
                      "confidence": "EXTRACTED", "source_file": definition["source_file"]})
    else:
        definition["metadata"]["cpp_constructor"]["owner_b64"] = "invalid!"
    bind_cpp_constructors(nodes, edges)
    assert not definition["metadata"]["cpp_constructor"].get("owner_bound")
    assert not constructor_merge_allowed([prototype, definition])


def test_req_qml008_ac02_long_qualified_owner_stays_bounded_through_metadata_sanitation(tmp_path):
    """Oversized identifiers cannot be silently truncated into another constructor owner."""
    namespace = "N" * 385
    paths = corpus(tmp_path, f"namespace {namespace} {{ class Backend {{public: Backend(int initial);}}; }}",
                   f"{namespace}::Backend::Backend(int initial) {{}}")
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    definition = next(node for node in result["nodes"] if node.get("_callable") and node["source_file"] == "backend.cpp")
    assert not owner_edges(result, definition)


def test_req_qml008_ac02_corrupted_owner_cannot_relabel_another_actual_constructor(tmp_path):
    """Changing only copied owner transport must never bind an Impostor body to Genuine."""
    paths = corpus(tmp_path, "class Genuine {public: Genuine(int value);};", "Impostor::Impostor(int value) {}")
    results = [extract_cpp(path) for path in paths]
    nodes = copy.deepcopy([node for result in results for node in result["nodes"]])
    edges = copy.deepcopy([edge for result in results for edge in result["edges"]])
    definition = next(node for node in nodes if node.get("metadata", {}).get("cpp_constructor", {}).get("role") == "definition")
    definition["metadata"]["cpp_constructor"]["owner_b64"] = base64.b64encode(b"Genuine").decode()
    bind_cpp_constructors(nodes, edges)
    assert not definition["metadata"]["cpp_constructor"].get("owner_bound")
    assert not owner_edges({"edges": edges}, definition)


def test_req_qml008_ac02_reference_parameter_names_do_not_change_constructor_type_proof(tmp_path):
    """Different parameter names retain the same reference type without erasing word tokens."""
    paths = corpus(tmp_path, "class Backend {public: Backend(const int &left);};", "Backend::Backend(const int &right) {}")
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    definition = next(node for node in result["nodes"] if node.get("definition_file") == "backend.cpp")
    assert owner_edges(result, definition)


def test_req_qml008_ac02_generic_constructor_facts_keep_original_bom_crlf_unicode_spans(tmp_path):
    """Class, prototype and implementation metadata spans all address the original disk bytes."""
    header = "\ufeff// caf\u00e9 \u96ea\r\nclass Backend {\r\npublic:\r\n explicit Backend(const int &left);\r\n};\r\n"
    implementation = "\ufeff// caf\u00e9 \u96ea\r\nBackend::Backend(const int &right) {}\r\n"
    paths = [tmp_path / "backend.hpp", tmp_path / "backend.cpp"]
    for path, source in zip(paths, (header, implementation)):
        path.write_bytes(source.encode("utf-8"))
    for path, expected in zip(paths, ((b"class Backend {\r\npublic:\r\n explicit Backend(const int &left);\r\n}",
                                     b"explicit Backend(const int &left);"), (b"Backend::Backend(const int &right) {}",))):
        result = extract_cpp(path)
        slices = []
        for node in result["nodes"]:
            for key in ("cpp_class", "cpp_constructor"):
                fact = node.get("metadata", {}).get(key)
                if fact:
                    span = fact["span"]
                    slices.append(path.read_bytes()[span["start_byte"]:span["end_byte"]])
        assert slices == list(expected)


def test_req_qml008_ac02_corrupted_namespace_owner_cannot_escape_original_lexical_scope(tmp_path):
    """A copied owner field cannot redirect a Shared constructor into an accepted Other class."""
    paths = [tmp_path / "shared.hpp", tmp_path / "other.hpp", tmp_path / "backend.cpp"]
    sources = ["namespace Shared {class Backend {public: Backend(int value);};}",
               "namespace Other {class Backend {public: Backend(int value);};}",
               "namespace Shared { Backend::Backend(int value) {} }"]
    for path, source in zip(paths, sources):
        path.write_text(source, encoding="utf-8")
    results = [extract_cpp(path) for path in paths]
    nodes = copy.deepcopy([node for result in results for node in result["nodes"]])
    edges = copy.deepcopy([edge for result in results for edge in result["edges"]])
    definition = next(node for node in nodes if node.get("metadata", {}).get("cpp_constructor", {}).get("role") == "definition")
    definition["metadata"]["cpp_constructor"]["owner_b64"] = base64.b64encode(b"Other::Backend").decode()
    bind_cpp_constructors(nodes, edges)
    assert not definition["metadata"]["cpp_constructor"].get("owner_bound")
    assert not owner_edges({"edges": edges}, definition)


@pytest.mark.parametrize("source", ["namespace {class Backend {public: Backend(int value);}; Backend::Backend(int value) {}}",
                                    "struct {int value;} unnamed; int helper(){return 1;}"])
def test_req_qml008_ac02_anonymous_cpp_scopes_do_not_break_generic_extraction(tmp_path, source):
    """Unsupported anonymous constructor scopes keep ordinary C++ output without producer exceptions."""
    path = tmp_path / "anonymous.cpp"
    path.write_text(source, encoding="utf-8")
    result = extract_cpp(path)
    assert not result.get("error") and not result.get("parse_errors")
    assert result["nodes"]
    assert not any(node.get("metadata", {}).get("cpp_constructor") for node in result["nodes"])
