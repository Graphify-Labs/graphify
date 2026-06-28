"""Tests for language extractors: Java, C, C++, Ruby, C#, Kotlin, Scala, PHP, Swift, Go, Julia, Fortran, JS/TS, .NET project files, XAML."""
from __future__ import annotations
from pathlib import Path
import pytest
from graphify.extract import (
    extract_java, extract_c, extract_cpp, extract_ruby,
    extract_csharp, extract_kotlin, extract_scala, extract_php,
    extract_swift, extract_go, extract_julia, extract_js, extract_fortran,
    extract_groovy, extract_sln, extract_csproj, extract_xaml, extract_razor,
    extract_dm, extract_dmi, extract_dmm, extract_dmf,
    extract_powershell, extract_apex, extract_verilog,
    extract_powershell_manifest,
)

FIXTURES = Path(__file__).parent / "fixtures"

# tree-sitter-dm is an optional extra (#1104) - it ships no Linux/Mac wheel, so it
# is not installed by a default `uv sync`. Skip the .dm/.dme grammar tests when the
# grammar is absent (.dmi/.dmm/.dmf use no tree-sitter and are always tested).
import importlib.util as _ilu
_needs_dm = pytest.mark.skipif(
    _ilu.find_spec("tree_sitter_dm") is None,
    reason="tree-sitter-dm not installed (optional [dm] extra)",
)


def _labels(r):
    return [n["label"] for n in r["nodes"]]

def _relations(r):
    return {e["relation"] for e in r["edges"]}

def _calls(r):
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (node_by_id.get(e["source"], e["source"]), node_by_id.get(e["target"], e["target"]))
        for e in r["edges"] if e["relation"] == "calls"
    }


def _references(r):
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    return [
        (
            node_by_id.get(e["source"], e["source"]),
            node_by_id.get(e["target"], e["target"]),
            e,
        )
        for e in r["edges"] if e["relation"] == "references"
    ]


def _edges_with_relation(r, *relations):
    return [e for e in r["edges"] if e["relation"] in relations]


def _normalize_symbol_label(label: str) -> str:
    return label.strip("()").lstrip(".")


def _node_by_label(result: dict, label: str) -> dict:
    for node in result["nodes"]:
        if node.get("label") == label or _normalize_symbol_label(node.get("label", "")) == label:
            return node
    raise AssertionError(f"missing node label {label!r}")


def _edge_labels(result: dict, relation: str, context: str | None = None) -> set[tuple[str, str]]:
    labels = {node["id"]: _normalize_symbol_label(node["label"]) for node in result["nodes"]}
    pairs = set()
    for edge in result["edges"]:
        if edge.get("relation") != relation:
            continue
        if context is not None and edge.get("context") != context:
            continue
        pairs.add((labels.get(edge["source"], edge["source"]), labels.get(edge["target"], edge["target"])))
    return pairs


# ── Java ──────────────────────────────────────────────────────────────────────

def test_java_no_error():
    r = extract_java(FIXTURES / "sample.java")
    assert "error" not in r

def test_java_finds_class():
    r = extract_java(FIXTURES / "sample.java")
    assert any("DataProcessor" in l for l in _labels(r))

def test_java_finds_interface():
    r = extract_java(FIXTURES / "sample.java")
    assert any("Processor" in l for l in _labels(r))

def test_java_finds_methods():
    r = extract_java(FIXTURES / "sample.java")
    labels = _labels(r)
    assert any("addItem" in l for l in labels)
    assert any("process" in l for l in labels)

def test_java_finds_imports():
    r = extract_java(FIXTURES / "sample.java")
    assert "imports" in _relations(r)


def test_java_import_edges_have_import_context():
    r = extract_java(FIXTURES / "sample.java")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)

def test_java_no_dangling_edges():
    r = extract_java(FIXTURES / "sample.java")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids


# ── C ────────────────────────────────────────────────────────────────────────

def test_c_no_error():
    r = extract_c(FIXTURES / "sample.c")
    assert "error" not in r

def test_c_finds_functions():
    r = extract_c(FIXTURES / "sample.c")
    labels = _labels(r)
    assert any("process" in l for l in labels)
    assert any("main" in l for l in labels)

def test_c_finds_includes():
    r = extract_c(FIXTURES / "sample.c")
    assert "imports" in _relations(r)

def test_c_emits_calls():
    r = extract_c(FIXTURES / "sample.c")
    assert any(e["relation"] == "calls" for e in r["edges"])

def test_c_calls_are_extracted():
    r = extract_c(FIXTURES / "sample.c")
    for e in r["edges"]:
        if e["relation"] == "calls":
            assert e["confidence"] == "EXTRACTED"


def test_c_import_edges_have_import_context():
    r = extract_c(FIXTURES / "sample.c")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_c_parameter_and_return_type_contexts():
    r = extract_c(FIXTURES / "sample.c")
    assert ("make_rect", "Rectangle") in _edge_labels(r, "references", "parameter_type")
    assert ("make_rect", "Rectangle") in _edge_labels(r, "references", "return_type")


def test_c_call_edges_have_call_context():
    r = extract_c(FIXTURES / "sample.c")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)


# ── C++ ───────────────────────────────────────────────────────────────────────

def test_cpp_no_error():
    r = extract_cpp(FIXTURES / "sample.cpp")
    assert "error" not in r

def test_cpp_finds_class():
    r = extract_cpp(FIXTURES / "sample.cpp")
    assert any("HttpClient" in l for l in _labels(r))

def test_cpp_finds_methods():
    r = extract_cpp(FIXTURES / "sample.cpp")
    labels = _labels(r)
    # C++ extractor captures the constructor and public-visible methods
    assert any("HttpClient" in l for l in labels)

def test_cpp_finds_includes():
    r = extract_cpp(FIXTURES / "sample.cpp")
    assert "imports" in _relations(r)


def test_cpp_import_edges_have_import_context():
    r = extract_cpp(FIXTURES / "sample.cpp")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_cpp_method_parameter_and_return_type_contexts():
    r = extract_cpp(FIXTURES / "sample.cpp")
    assert ("get", "string") in _edge_labels(r, "references", "parameter_type")
    assert ("get", "string") in _edge_labels(r, "references", "return_type")


def test_cpp_field_and_template_argument_contexts():
    r = extract_cpp(FIXTURES / "sample.cpp")
    assert ("HttpClient", "string") in _edge_labels(r, "references", "field")
    assert ("HttpClient", "vector") in _edge_labels(r, "references", "field")
    assert ("HttpClient", "string") in _edge_labels(r, "references", "generic_arg")


def test_cpp_class_inherits_edge():
    """Regression for #915: `class Derived : public Base {}` should emit an inherits edge."""
    r = extract_cpp(FIXTURES / "sample.cpp")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    found = any(
        "AuthedHttpClient" in node_by_id.get(e["source"], "")
        and "HttpClient" in node_by_id.get(e["target"], "")
        for e in r["edges"] if e["relation"] == "inherits"
    )
    assert found, "AuthedHttpClient should have inherits edge to HttpClient"


def test_cpp_struct_inherits_edge():
    """Structs use the same `: Base` syntax as classes and must also emit inherits."""
    r = extract_cpp(FIXTURES / "sample.cpp")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    found = any(
        "RetryingHttpClient" in node_by_id.get(e["source"], "")
        and "HttpClient" in node_by_id.get(e["target"], "")
        for e in r["edges"] if e["relation"] == "inherits"
    )
    assert found, "RetryingHttpClient (struct) should have inherits edge to HttpClient"


# ── CUDA ──────────────────────────────────────────────────────────────────────
# CUDA is a C++ superset, so .cu/.cuh route through the C++ (tree-sitter-cpp)
# extractor. These tests guard that __global__/__device__ kernels, host
# functions, structs and includes are all extracted.

def test_cuda_no_error():
    r = extract_cpp(FIXTURES / "sample.cu")
    assert "error" not in r

def test_cuda_finds_kernel_and_device_functions():
    r = extract_cpp(FIXTURES / "sample.cu")
    labels = _labels(r)
    assert any("saxpy" in l for l in labels)   # __global__ kernel
    assert any("dot" in l for l in labels)     # __device__ function

def test_cuda_finds_struct():
    r = extract_cpp(FIXTURES / "sample.cu")
    assert any("Vec3" in l for l in _labels(r))

def test_cuda_finds_includes():
    r = extract_cpp(FIXTURES / "sample.cu")
    assert "imports" in _relations(r)

def test_cuda_host_call_edges():
    r = extract_cpp(FIXTURES / "sample.cu")
    calls = _calls(r)
    assert ("host_norm()", "dot()") in calls
    assert ("main()", "host_norm()") in calls


# Metal Shading Language is a C++14-derived language, so .metal files route
# through the C++ extractor just like CUDA does.

def test_metal_is_code_extension():
    from graphify.detect import CODE_EXTENSIONS
    assert ".metal" in CODE_EXTENSIONS


def test_metal_no_error():
    r = extract_cpp(FIXTURES / "sample.metal")
    assert "error" not in r


def test_metal_finds_kernel_function_and_struct():
    r = extract_cpp(FIXTURES / "sample.metal")
    labels = _labels(r)
    assert any("Vec3" in l for l in labels)
    assert any("dot3" in l for l in labels)
    assert any("saxpy" in l for l in labels)


# ── Ruby ─────────────────────────────────────────────────────────────────────

def test_ruby_no_error():
    r = extract_ruby(FIXTURES / "sample.rb")
    assert "error" not in r

def test_ruby_finds_class():
    r = extract_ruby(FIXTURES / "sample.rb")
    assert any("ApiClient" in l for l in _labels(r))

def test_ruby_finds_methods():
    r = extract_ruby(FIXTURES / "sample.rb")
    labels = _labels(r)
    assert any("get" in l for l in labels)
    assert any("post" in l for l in labels)

def test_ruby_finds_function():
    r = extract_ruby(FIXTURES / "sample.rb")
    assert any("parse_response" in l for l in _labels(r))


# ── C# ───────────────────────────────────────────────────────────────────────

def test_csharp_no_error():
    r = extract_csharp(FIXTURES / "sample.cs")
    assert "error" not in r

def test_csharp_finds_class():
    r = extract_csharp(FIXTURES / "sample.cs")
    assert any("DataProcessor" in l for l in _labels(r))

def test_csharp_finds_interface():
    r = extract_csharp(FIXTURES / "sample.cs")
    assert any("IProcessor" in l for l in _labels(r))

def test_csharp_finds_methods():
    r = extract_csharp(FIXTURES / "sample.cs")
    labels = _labels(r)
    assert any("Process" in l for l in labels)

def test_csharp_finds_usings():
    r = extract_csharp(FIXTURES / "sample.cs")
    assert "imports" in _relations(r)

def test_csharp_inherits_edge():
    r = extract_csharp(FIXTURES / "sample.cs")
    inherits = [e for e in r["edges"] if e["relation"] == "inherits"]
    assert len(inherits) >= 1

def test_csharp_implements_iprocessor():
    r = extract_csharp(FIXTURES / "sample.cs")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    found = any(
        "DataProcessor" in node_by_id.get(e["source"], "") and
        "IProcessor" in node_by_id.get(e["target"], "")
        for e in r["edges"] if e["relation"] == "implements"
    )
    assert found, "DataProcessor should have implements edge to IProcessor"


def test_csharp_splits_inherits_and_implements_edges():
    result = extract_csharp(FIXTURES / "sample.cs")
    assert ("DataProcessor", "Processor") in _edge_labels(result, "inherits")
    assert ("DataProcessor", "IProcessor") in _edge_labels(result, "implements")


def test_csharp_parameter_return_and_generic_contexts():
    result = extract_csharp(FIXTURES / "sample.cs")
    assert ("Build", "HttpClient") in _edge_labels(result, "references", "parameter_type")
    assert ("Build", "Result") in _edge_labels(result, "references", "return_type")
    assert ("Build", "DataProcessor") in _edge_labels(result, "references", "generic_arg")


def test_java_normalizes_inherits_and_implements():
    result = extract_java(FIXTURES / "sample.java")
    assert ("DataProcessor", "BaseProcessor") in _edge_labels(result, "inherits")
    assert ("DataProcessor", "Processor") in _edge_labels(result, "implements")


def test_java_generic_parents_include_type_argument_references(tmp_path):
    source = tmp_path / "GenericParents.java"
    source.write_text(
        "class Dependency {}\n"
        "interface Event {}\n"
        "class Base<T> {}\n"
        "interface Handler<T> {}\n"
        "interface DerivedHandler extends Handler<Event> {}\n"
        "class Service extends Base<Dependency> implements Handler<Event> {}\n"
    )

    result = extract_java(source)

    assert ("Service", "Base") in _edge_labels(result, "inherits")
    assert ("Service", "Handler") in _edge_labels(result, "implements")
    refs = _edge_labels(result, "references", "generic_arg")
    assert ("Service", "Dependency") in refs
    assert ("Service", "Event") in refs
    assert ("DerivedHandler", "Handler") in _edge_labels(result, "inherits")
    assert ("DerivedHandler", "Event") in refs


def test_java_type_parameters_do_not_emit_references(tmp_path):
    source = tmp_path / "TypeParameters.java"
    source.write_text(
        "class Payload {}\n"
        "class Base<X> {}\n"
        "class Box<T> extends Base<T> {\n"
        "    T value;\n"
        "    List<T> values;\n"
        "    <U> U convert(T input, List<U> mapped, List<Payload> retained) {\n"
        "        return null;\n"
        "    }\n"
        "    <V> Box(V value) {}\n"
        "}\n"
    )

    result = extract_java(source)

    references = _references(result)
    assert not [edge for _, target, edge in references if target in {"T", "U", "V"}]
    assert not [
        node
        for node in result["nodes"]
        if node.get("label") in {"T", "U", "V"} and not node.get("source_file")
    ]
    assert ("Box", "Base") in _edge_labels(result, "inherits")
    assert ("convert", "Payload") in _edge_labels(result, "references", "generic_arg")


def test_java_parameter_return_generic_and_attribute_contexts():
    result = extract_java(FIXTURES / "sample.java")
    assert ("build", "HttpClient") in _edge_labels(result, "references", "parameter_type")
    assert ("build", "Result") in _edge_labels(result, "references", "return_type")
    assert ("build", "DataProcessor") in _edge_labels(result, "references", "generic_arg")
    assert ("build", "Override") in _edge_labels(result, "references", "attribute")


def test_java_field_type_references_have_field_context(tmp_path):
    source = tmp_path / "Fields.java"
    source.write_text(
        "class PaymentGateway {}\n"
        "class Handler {}\n"
        "class CheckoutService {\n"
        "    PaymentGateway gateway;\n"
        "    List<Handler> handlers;\n"
        "}\n"
    )
    result = extract_java(source)
    assert ("CheckoutService", "PaymentGateway") in _edge_labels(
        result, "references", "field"
    )
    assert ("CheckoutService", "Handler") in _edge_labels(
        result, "references", "generic_arg"
    )


def test_java_record_component_type_references(tmp_path):
    source = tmp_path / "RecordComponents.java"
    source.write_text(
        "class Payload {}\n"
        "class Item {}\n"
        "class Attachment {}\n"
        "record Order(Payload payload, List<Item> items, int count, "
        "Attachment... attachments) {}\n"
    )

    result = extract_java(source)

    assert ("Order", "Payload") in _edge_labels(result, "references", "field")
    assert ("Order", "List") in _edge_labels(result, "references", "field")
    assert ("Order", "Item") in _edge_labels(result, "references", "generic_arg")
    assert ("Order", "Attachment") in _edge_labels(result, "references", "field")


def test_java_record_components_skip_type_parameters(tmp_path):
    source = tmp_path / "GenericRecord.java"
    source.write_text(
        "class Payload {}\n"
        "class Box<X> {}\n"
        "record Batch<T>(T value, Box<T> boxed, Box<Payload> retained) {}\n"
    )

    result = extract_java(source)

    assert ("Batch", "T") not in _edge_labels(result, "references")
    assert not [
        node
        for node in result["nodes"]
        if node.get("label") == "T" and not node.get("source_file")
    ]
    assert ("Batch", "Box") in _edge_labels(result, "references", "field")
    assert ("Batch", "Payload") in _edge_labels(result, "references", "generic_arg")


def test_java_type_annotations_have_attribute_context(tmp_path):
    source = tmp_path / "TypeAnnotations.java"
    source.write_text(
        '@Service\n'
        '@Entity(name = "checkout")\n'
        'class CheckoutService {}\n'
    )

    result = extract_java(source)

    refs = _edge_labels(result, "references", "attribute")
    assert ("CheckoutService", "Service") in refs
    assert ("CheckoutService", "Entity") in refs


def test_java_enum_and_annotation_declarations_are_type_nodes(tmp_path):
    source = tmp_path / "TypeDeclarations.java"
    source.write_text(
        "enum PaymentStatus { PENDING, PAID }\n"
        "@interface Audited {}\n"
        "class Order { PaymentStatus status; }\n"
        "@Audited class CheckoutService {}\n"
    )

    result = extract_java(source)

    assert ("TypeDeclarations.java", "PaymentStatus") in _edge_labels(
        result, "contains"
    )
    assert ("TypeDeclarations.java", "Audited") in _edge_labels(result, "contains")
    assert ("Order", "PaymentStatus") in _edge_labels(
        result, "references", "field"
    )
    assert ("CheckoutService", "Audited") in _edge_labels(
        result, "references", "attribute"
    )
    definitions = {
        node["label"]: node
        for node in result["nodes"]
        if node.get("label") in {"PaymentStatus", "Audited"}
    }
    assert definitions["PaymentStatus"].get("source_file") == str(source)
    assert definitions["Audited"].get("source_file") == str(source)


def test_csharp_field_type_references_have_field_context():
    r = extract_csharp(FIXTURES / "sample.cs")
    refs = _references(r)
    assert any(
        "DataProcessor" in src and "HttpClient" in tgt and edge.get("context") == "field"
        for src, tgt, edge in refs
    ), "DataProcessor field declarations should reference HttpClient with field context"


def test_csharp_call_edges_have_call_context():
    r = extract_csharp(FIXTURES / "sample.cs")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    assert any(
        "Process" in node_by_id.get(e["source"], "")
        and "Validate" in node_by_id.get(e["target"], "")
        and e.get("context") == "call"
        for e in r["edges"] if e["relation"] == "calls"
    ), "C# call edges should retain call context"


def test_csharp_import_edges_have_import_context():
    r = extract_csharp(FIXTURES / "sample.cs")
    import_edges = [e for e in r["edges"] if e["relation"] == "imports"]
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


# ── Kotlin ───────────────────────────────────────────────────────────────────

def test_kotlin_no_error():
    r = extract_kotlin(FIXTURES / "sample.kt")
    assert "error" not in r

def test_kotlin_finds_class():
    r = extract_kotlin(FIXTURES / "sample.kt")
    assert any("HttpClient" in l for l in _labels(r))

def test_kotlin_finds_data_class():
    r = extract_kotlin(FIXTURES / "sample.kt")
    assert any("Config" in l for l in _labels(r))

def test_kotlin_finds_methods():
    r = extract_kotlin(FIXTURES / "sample.kt")
    labels = _labels(r)
    assert any("get" in l for l in labels)
    assert any("post" in l for l in labels)

def test_kotlin_finds_function():
    r = extract_kotlin(FIXTURES / "sample.kt")
    assert any("createClient" in l for l in _labels(r))

def test_kotlin_emits_in_file_calls():
    """Regression test for the call-walker `simple_identifier` /
    `identifier` rename — see graphify-kmp's PythonParityTest."""
    r = extract_kotlin(FIXTURES / "sample.kt")
    calls = _calls(r)
    # In sample.kt: get() and post() both call buildRequest(), and
    # createClient() invokes Config and HttpClient (constructor calls).
    assert (".get()", ".buildRequest()") in calls
    assert (".post()", ".buildRequest()") in calls
    assert ("createClient()", "Config") in calls
    assert ("createClient()", "HttpClient") in calls


def test_kotlin_splits_inherits_and_implements():
    r = extract_kotlin(FIXTURES / "sample.kt")
    assert ("DataProcessor", "BaseProcessor") in _edge_labels(r, "inherits")
    assert ("DataProcessor", "Loggable") in _edge_labels(r, "implements")


def test_kotlin_parameter_return_generic_and_field_contexts():
    r = extract_kotlin(FIXTURES / "sample.kt")
    assert ("run", "DataProcessor") in _edge_labels(r, "references", "parameter_type")
    assert ("run", "Result") in _edge_labels(r, "references", "return_type")
    assert ("run", "DataProcessor") in _edge_labels(r, "references", "generic_arg")
    assert ("DataProcessor", "Result") in _edge_labels(r, "references", "field")


# ── Scala ─────────────────────────────────────────────────────────────────────

def test_scala_no_error():
    r = extract_scala(FIXTURES / "sample.scala")
    assert "error" not in r

def test_scala_finds_class():
    r = extract_scala(FIXTURES / "sample.scala")
    assert any("HttpClient" in l for l in _labels(r))

def test_scala_finds_object():
    r = extract_scala(FIXTURES / "sample.scala")
    assert any("HttpClientFactory" in l for l in _labels(r))

def test_scala_finds_methods():
    r = extract_scala(FIXTURES / "sample.scala")
    labels = _labels(r)
    assert any("get" in l for l in labels)
    assert any("post" in l for l in labels)


def test_scala_import_edges_have_import_context():
    r = extract_scala(FIXTURES / "sample.scala")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_scala_splits_inherits_and_mixes_in():
    r = extract_scala(FIXTURES / "sample.scala")
    assert ("HttpClient", "BaseClient") in _edge_labels(r, "inherits")
    assert ("HttpClient", "Loggable") in _edge_labels(r, "mixes_in")


def test_scala_constructor_parameter_field_context():
    r = extract_scala(FIXTURES / "sample.scala")
    assert ("HttpClient", "Config") in _edge_labels(r, "references", "field")


def test_scala_val_definition_field_context():
    r = extract_scala(FIXTURES / "sample.scala")
    assert ("HttpClient", "Config") in _edge_labels(r, "references", "field")


def test_scala_method_return_type_context():
    r = extract_scala(FIXTURES / "sample.scala")
    assert ("create", "HttpClient") in _edge_labels(r, "references", "return_type")


def test_scala_call_edges_have_call_context():
    r = extract_scala(FIXTURES / "sample.scala")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)


# ── PHP ───────────────────────────────────────────────────────────────────────

def test_php_no_error():
    r = extract_php(FIXTURES / "sample.php")
    assert "error" not in r

def test_php_finds_class():
    r = extract_php(FIXTURES / "sample.php")
    assert any("ApiClient" in l for l in _labels(r))

def test_php_finds_methods():
    r = extract_php(FIXTURES / "sample.php")
    labels = _labels(r)
    assert any("get" in l for l in labels)
    assert any("post" in l for l in labels)

def test_php_finds_function():
    r = extract_php(FIXTURES / "sample.php")
    assert any("parseResponse" in l for l in _labels(r))

def test_php_finds_imports():
    r = extract_php(FIXTURES / "sample.php")
    assert "imports" in _relations(r)


def test_php_import_edges_have_import_context():
    r = extract_php(FIXTURES / "sample.php")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_php_call_edges_have_call_context():
    r = extract_php(FIXTURES / "sample.php")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)

def test_php_finds_static_property_access():
    r = extract_php(FIXTURES / "sample_php_static_prop.php")
    assert "uses_static_prop" in _relations(r)

def test_php_static_prop_target_is_holding_class():
    r = extract_php(FIXTURES / "sample_php_static_prop.php")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    uses_prop = [
        (node_by_id.get(e["source"], e["source"]), node_by_id.get(e["target"], e["target"]))
        for e in r["edges"] if e["relation"] == "uses_static_prop"
    ]
    assert any("DefaultPalette" in tgt for _, tgt in uses_prop)

def test_php_finds_config_helper_call():
    r = extract_php(FIXTURES / "sample_php_config.php")
    assert "uses_config" in _relations(r)

def test_php_config_helper_target_matches_first_segment():
    r = extract_php(FIXTURES / "sample_php_config.php")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    uses_cfg = [
        (node_by_id.get(e["source"], e["source"]), node_by_id.get(e["target"], e["target"]))
        for e in r["edges"] if e["relation"] == "uses_config"
    ]
    assert any("Throttle" in tgt for _, tgt in uses_cfg)

def test_php_finds_container_bind():
    r = extract_php(FIXTURES / "sample_php_container.php")
    assert "bound_to" in _relations(r)

def test_php_container_bind_links_contract_to_implementation():
    r = extract_php(FIXTURES / "sample_php_container.php")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    bound = [
        (node_by_id.get(e["source"], e["source"]), node_by_id.get(e["target"], e["target"]))
        for e in r["edges"] if e["relation"] == "bound_to"
    ]
    assert any("PaymentGateway" in src and "StripeGateway" in tgt for src, tgt in bound)

def test_php_finds_event_listeners():
    r = extract_php(FIXTURES / "sample_php_listen.php")
    assert "listened_by" in _relations(r)

def test_php_event_listener_links_event_to_listener():
    r = extract_php(FIXTURES / "sample_php_listen.php")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    listened = [
        (node_by_id.get(e["source"], e["source"]), node_by_id.get(e["target"], e["target"]))
        for e in r["edges"] if e["relation"] == "listened_by"
    ]
    assert any("UserRegistered" in src and "SendWelcomeEmail" in tgt for src, tgt in listened)


def test_php_splits_inherits_implements_mixes_in():
    r = extract_php(FIXTURES / "sample.php")
    assert ("DataProcessor", "BaseProcessor") in _edge_labels(r, "inherits")
    assert ("DataProcessor", "Loggable") in _edge_labels(r, "implements")
    assert ("DataProcessor", "HasName") in _edge_labels(r, "mixes_in")


def test_php_property_parameter_and_return_contexts():
    r = extract_php(FIXTURES / "sample.php")
    assert ("DataProcessor", "Result") in _edge_labels(r, "references", "field")
    assert ("run", "DataProcessor") in _edge_labels(r, "references", "parameter_type")
    assert ("run", "Result") in _edge_labels(r, "references", "return_type")


# ── Swift ────────────────────────────────────────────────────────────────────

def test_swift_no_error():
    r = extract_swift(FIXTURES / "sample.swift")
    assert "error" not in r

def test_swift_finds_class():
    r = extract_swift(FIXTURES / "sample.swift")
    assert any("DataProcessor" in l for l in _labels(r))

def test_swift_finds_protocol():
    r = extract_swift(FIXTURES / "sample.swift")
    assert any("Processor" in l for l in _labels(r))

def test_swift_finds_struct():
    r = extract_swift(FIXTURES / "sample.swift")
    assert any("Config" in l for l in _labels(r))

def test_swift_finds_methods():
    r = extract_swift(FIXTURES / "sample.swift")
    labels = _labels(r)
    assert any("addItem" in l for l in labels)
    assert any("process" in l for l in labels)

def test_swift_finds_function():
    r = extract_swift(FIXTURES / "sample.swift")
    assert any("createProcessor" in l for l in _labels(r))

def test_swift_finds_imports():
    r = extract_swift(FIXTURES / "sample.swift")
    assert "imports" in _relations(r)


def test_swift_import_edges_have_import_context():
    r = extract_swift(FIXTURES / "sample.swift")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)

def test_swift_no_dangling_edges():
    r = extract_swift(FIXTURES / "sample.swift")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids
        # #1327: targets must resolve to a node too, else build.py prunes the edge.
        assert e["target"] in node_ids, f"dangling target {e['target']} ({e['relation']})"


def test_swift_imports_survive_build():
    # #1327: `import Foundation` / `import UIKit` previously emitted edges to bare
    # module ids with no backing node, so build.py dropped 100% of Swift imports.
    from graphify.build import build_from_json
    r = extract_swift(FIXTURES / "sample.swift")
    import_edges = [e for e in r["edges"] if e["relation"] == "imports"]
    assert import_edges, "extractor should emit Swift import edges"
    node_ids = {n["id"] for n in r["nodes"]}
    for e in import_edges:
        assert e["target"] in node_ids  # synthesized module node exists
    # Imported modules are tagged type=module (anchor nodes, #1327/#1330).
    module_labels = {n["label"] for n in r["nodes"] if n.get("type") == "module"}
    assert {"Foundation", "UIKit"} <= module_labels
    # No private bookkeeping key should leak into output edges.
    assert all("_import_label" not in e for e in r["edges"])
    # Edges must survive the build (which prunes edges with unknown endpoints).
    G = build_from_json(r)
    surviving = [
        (u, v) for u, v, d in G.edges(data=True) if d.get("relation") == "imports"
    ]
    assert surviving, "Swift import edges must survive build_from_json (#1327)"

def test_swift_finds_actor():
    r = extract_swift(FIXTURES / "sample.swift")
    assert any("CacheManager" in l for l in _labels(r))

def test_swift_finds_enum():
    r = extract_swift(FIXTURES / "sample.swift")
    assert any("NetworkError" in l for l in _labels(r))

def test_swift_finds_enum_methods():
    r = extract_swift(FIXTURES / "sample.swift")
    assert any("describe" in l for l in _labels(r))

def test_swift_finds_enum_cases():
    r = extract_swift(FIXTURES / "sample.swift")
    labels = _labels(r)
    assert any("timeout" in l for l in labels)
    assert any("connectionFailed" in l for l in labels)

def test_swift_enum_cases_have_case_of_edge():
    r = extract_swift(FIXTURES / "sample.swift")
    case_edges = [e for e in r["edges"] if e["relation"] == "case_of"]
    assert len(case_edges) >= 2

def test_swift_finds_deinit():
    r = extract_swift(FIXTURES / "sample.swift")
    assert any("deinit" in l for l in _labels(r))

def test_swift_finds_subscript():
    r = extract_swift(FIXTURES / "sample.swift")
    assert any("subscript" in l for l in _labels(r))

def test_swift_extension_methods_attach_to_type():
    r = extract_swift(FIXTURES / "sample.swift")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    method_edges = [e for e in r["edges"] if e["relation"] == "method"]
    found = False
    for e in method_edges:
        src_label = node_by_id.get(e["source"], "")
        tgt_label = node_by_id.get(e["target"], "")
        if "Config" in src_label and "isValid" in tgt_label:
            found = True
            break
    assert found, "extension method isValid should attach to Config"

def test_swift_extension_does_not_duplicate_type_node():
    r = extract_swift(FIXTURES / "sample.swift")
    config_nodes = [n for n in r["nodes"] if n["label"] == "Config"]
    assert len(config_nodes) == 1, f"Config should appear once, got {len(config_nodes)}"

def test_swift_protocol_conformance_emits_implements():
    r = extract_swift(FIXTURES / "sample.swift")
    assert ("DataProcessor", "Processor") in _edge_labels(r, "implements")


def test_swift_extension_conformance_emits_implements():
    r = extract_swift(FIXTURES / "sample.swift")
    assert ("DataProcessor", "Loggable") in _edge_labels(r, "implements")


def test_swift_splits_inherits_and_implements():
    r = extract_swift(FIXTURES / "sample.swift")
    assert ("DataProcessor", "BaseProcessor") in _edge_labels(r, "inherits")
    assert ("DataProcessor", "Processor") in _edge_labels(r, "implements")


def test_swift_parameter_return_generic_and_field_contexts():
    r = extract_swift(FIXTURES / "sample.swift")
    assert ("run", "DataProcessor") in _edge_labels(r, "references", "parameter_type")
    assert ("run", "Result") in _edge_labels(r, "references", "return_type")
    assert ("run", "DataProcessor") in _edge_labels(r, "references", "generic_arg")
    assert ("DataProcessor", "Result") in _edge_labels(r, "references", "field")

def test_swift_emits_calls():
    r = extract_swift(FIXTURES / "sample.swift")
    calls = _calls(r)
    assert any("process" in src and "validate" in tgt for src, tgt in calls)

def test_swift_call_edges_have_call_context():
    r = extract_swift(FIXTURES / "sample.swift")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)


def test_swift_extension_across_files_merges_into_canonical_type():
    """`extension Foo` in a separate file from `class Foo` must resolve to a
    single Foo node. tree-sitter-swift parses both as `class_declaration` and
    node ids carry the file stem, so without a corpus-level merge each file
    would emit its own Foo."""
    from graphify.extract import extract
    paths = sorted((FIXTURES / "swift_cross_file").glob("*.swift"))
    r = extract(paths, cache_root=Path("/tmp/graphify-test-no-cache"))
    foo_nodes = [n for n in r["nodes"] if n["label"] == "Foo"]
    assert len(foo_nodes) == 1, f"Foo should appear once, got {len(foo_nodes)}: {[n['id'] for n in foo_nodes]}"
    foo_id = foo_nodes[0]["id"]
    method_targets = {
        e["target"] for e in r["edges"]
        if e["relation"] == "method" and e["source"] == foo_id
    }
    method_labels = {n["label"] for n in r["nodes"] if n["id"] in method_targets}
    assert any("one" in l for l in method_labels), f"one() should attach to Foo, got {method_labels}"
    assert any("two" in l for l in method_labels), f"extension method two() should attach to Foo, got {method_labels}"


# ── Elixir ────────────────────────────────────────────────────────────────────

from graphify.extract import extract_elixir

def test_elixir_finds_module():
    r = extract_elixir(FIXTURES / "sample.ex")
    assert "error" not in r
    labels = [n["label"] for n in r["nodes"]]
    assert any("MyApp.Accounts.User" in l for l in labels)

def test_elixir_finds_functions():
    r = extract_elixir(FIXTURES / "sample.ex")
    labels = [n["label"] for n in r["nodes"]]
    assert any("create" in l for l in labels)
    assert any("find" in l for l in labels)
    assert any("validate" in l for l in labels)

def test_elixir_finds_imports():
    r = extract_elixir(FIXTURES / "sample.ex")
    import_edges = [e for e in r["edges"] if e["relation"] == "imports"]
    assert len(import_edges) >= 2


def test_elixir_import_edges_have_import_context():
    r = extract_elixir(FIXTURES / "sample.ex")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)

def test_elixir_finds_calls():
    r = extract_elixir(FIXTURES / "sample.ex")
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    labels = {n["id"]: n["label"] for n in r["nodes"]}
    assert any("create" in labels.get(src, "") and "validate" in labels.get(tgt, "") for src, tgt in calls)


def test_elixir_call_edges_have_call_context():
    r = extract_elixir(FIXTURES / "sample.ex")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)

def test_elixir_method_edges():
    r = extract_elixir(FIXTURES / "sample.ex")
    methods = [e for e in r["edges"] if e["relation"] == "method"]
    assert len(methods) >= 3


# ── Objective-C ──────────────────────────────────────────────────────────────
from graphify.extract import extract_objc


def test_objc_finds_interface():
    r = extract_objc(FIXTURES / "sample.m")
    labels = [n["label"] for n in r["nodes"]]
    assert "Animal" in labels


def test_objc_finds_subclass():
    r = extract_objc(FIXTURES / "sample.m")
    labels = [n["label"] for n in r["nodes"]]
    assert "Dog" in labels


def test_objc_finds_methods():
    r = extract_objc(FIXTURES / "sample.m")
    labels = [n["label"] for n in r["nodes"]]
    assert any("speak" in l or "fetch" in l or "initWithName" in l for l in labels)


def test_objc_finds_imports():
    r = extract_objc(FIXTURES / "sample.m")
    import_edges = [e for e in r["edges"] if e["relation"] == "imports"]
    assert len(import_edges) >= 1


def test_objc_import_edges_have_import_context():
    r = extract_objc(FIXTURES / "sample.m")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_objc_inherits_edge():
    r = extract_objc(FIXTURES / "sample.m")
    inherits = [e for e in r["edges"] if e["relation"] == "inherits"]
    assert len(inherits) >= 1


def test_objc_splits_inherits_and_implements():
    r = extract_objc(FIXTURES / "sample.m")
    assert ("Animal", "NSObject") in _edge_labels(r, "inherits")
    assert ("Dog", "Animal") in _edge_labels(r, "inherits")
    assert ("Animal", "SampleDelegate") in _edge_labels(r, "implements")


def test_objc_property_type_context():
    r = extract_objc(FIXTURES / "sample.m")
    assert ("Animal", "NSString") in _edge_labels(r, "references", "field")


def test_objc_no_dangling_edges():
    r = extract_objc(FIXTURES / "sample.m")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"Dangling source: {e}"


def test_objc_resolves_self_method_calls():
    """`[self speak]` inside Dog.fetch must produce a calls edge. The method-body
    second pass was dead code for ObjC because the grammar emits a simple selector
    as `identifier`, not `selector`/`keyword_argument_list` (#1475)."""
    r = extract_objc(FIXTURES / "sample.m")
    nid2label = {n["id"]: n["label"] for n in r["nodes"]}
    calls = [nid2label.get(e["target"]) for e in r["edges"] if e["relation"] == "calls"]
    assert any(t and "speak" in t for t in calls), calls


def test_objc_class_method_labeled_with_plus(tmp_path):
    """`+ (…)shared` is a class method and must be labeled +shared, not -shared (#1475)."""
    p = tmp_path / "S.m"
    p.write_text("@implementation S\n+ (instancetype)shared { return nil; }\n- (void)go { }\n@end\n")
    labels = {n["label"] for n in extract_objc(p)["nodes"]}
    assert "+shared" in labels and "-go" in labels


def test_objc_compound_selector_call_resolves(tmp_path):
    """A compound message `[self a:x b:y]` resolves to the compound method def (#1475)."""
    p = tmp_path / "V.m"
    p.write_text(
        "@implementation V\n"
        "- (void)tableView:(id)tv numberOfRowsInSection:(int)s { }\n"
        "- (void)go { [self tableView:nil numberOfRowsInSection:0]; }\n"
        "@end\n"
    )
    r = extract_objc(p)
    nid2label = {n["id"]: n["label"] for n in r["nodes"]}
    calls = [nid2label.get(e["target"]) for e in r["edges"] if e["relation"] == "calls"]
    assert any(t and "tableViewnumberOfRowsInSection" in t for t in calls), calls


def test_objc_generic_property_type_extracted(tmp_path):
    """`NSArray<Product *> *` must reference the element type Product (and the
    container NSArray); the generic wrapper made the type invisible before (#1475)."""
    p = tmp_path / "M.h"
    p.write_text("@interface M : NSObject\n@property (strong) NSArray<Product *> *items;\n@end\n")
    refs = _edge_labels(extract_objc(p), "references", "field")
    assert ("M", "Product") in refs
    assert ("M", "NSArray") in refs


def test_objc_module_import_edge(tmp_path):
    """`@import Foundation;` / `@import UIKit.UIView;` produce imports edges (#1475)."""
    from graphify.extract import _make_id
    p = tmp_path / "X.m"
    p.write_text("@import Foundation;\n@import UIKit.UIView;\n@implementation X\n@end\n")
    targets = {e["target"] for e in extract_objc(p)["edges"] if e["relation"] == "imports"}
    assert _make_id("Foundation") in targets and _make_id("UIKit") in targets


def test_objc_header_dispatch_routes_objc_not_c(tmp_path):
    """An ObjC `.h` (has @interface) routes to extract_objc; a plain C `.h` stays
    on extract_c, so C/C++ headers are never hijacked by the sniff (#1475)."""
    from graphify.extract import _get_extractor, extract_objc as _eo, extract_c as _ec
    objc_h = tmp_path / "AppDelegate.h"
    objc_h.write_text("@interface AppDelegate : NSObject <UIApplicationDelegate>\n@end\n")
    c_h = tmp_path / "util.h"
    c_h.write_text("#include <stdio.h>\nint add(int a, int b);\nstruct Point { int x; };\n")
    assert _get_extractor(objc_h) is _eo
    assert _get_extractor(c_h) is _ec


# ---------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------

def test_go_receiver_methods_share_type_node():
    """Methods on the same receiver type must share one canonical type node."""
    r = extract_go(FIXTURES / "sample.go")
    server_nodes = [n for n in r["nodes"] if n["label"] == "Server"]
    # Both Start() and Stop() are on *Server — should produce exactly one Server node
    assert len(server_nodes) == 1

def test_go_receiver_uses_pkg_scope():
    """Type node id should be scoped to directory, not file stem."""
    r = extract_go(FIXTURES / "sample.go")
    server_nodes = [n for n in r["nodes"] if n["label"] == "Server"]
    assert server_nodes
    # Should NOT contain the file stem "sample" in the type node id
    assert "sample" not in server_nodes[0]["id"].split(":")[0]


# ---------------------------------------------------------------------------
# Julia
# ---------------------------------------------------------------------------

def test_julia_finds_module():
    r = extract_julia(FIXTURES / "sample.jl")
    labels = [n["label"] for n in r["nodes"]]
    assert "Geometry" in labels


def test_julia_finds_structs():
    r = extract_julia(FIXTURES / "sample.jl")
    labels = [n["label"] for n in r["nodes"]]
    assert "Point" in labels
    assert "Circle" in labels


def test_julia_finds_abstract_type():
    r = extract_julia(FIXTURES / "sample.jl")
    labels = [n["label"] for n in r["nodes"]]
    assert "Shape" in labels


def test_julia_finds_functions():
    r = extract_julia(FIXTURES / "sample.jl")
    labels = [n["label"] for n in r["nodes"]]
    assert any("area" in l for l in labels)
    assert any("distance" in l for l in labels)


def test_julia_finds_short_function():
    r = extract_julia(FIXTURES / "sample.jl")
    labels = [n["label"] for n in r["nodes"]]
    assert any("perimeter" in l for l in labels)


def test_julia_finds_imports():
    r = extract_julia(FIXTURES / "sample.jl")
    import_edges = [e for e in r["edges"] if e["relation"] == "imports"]
    assert len(import_edges) >= 1


def test_julia_import_edges_have_import_context():
    r = extract_julia(FIXTURES / "sample.jl")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_julia_finds_inherits():
    r = extract_julia(FIXTURES / "sample.jl")
    inherits = [e for e in r["edges"] if e["relation"] == "inherits"]
    assert len(inherits) >= 1


def test_julia_abstract_concrete_hierarchy_inherits():
    r = extract_julia(FIXTURES / "sample.jl")
    assert ("Point", "Shape") in _edge_labels(r, "inherits")
    assert ("Circle", "Shape") in _edge_labels(r, "inherits")


def test_julia_struct_field_type_context():
    r = extract_julia(FIXTURES / "sample.jl")
    assert ("Point", "Float64") in _edge_labels(r, "references", "field")
    assert ("Circle", "Point") in _edge_labels(r, "references", "field")
    assert ("Circle", "Float64") in _edge_labels(r, "references", "field")


def test_julia_finds_calls():
    r = extract_julia(FIXTURES / "sample.jl")
    call_edges = [e for e in r["edges"] if e["relation"] == "calls"]
    assert len(call_edges) >= 1


def test_julia_call_edges_have_call_context():
    r = extract_julia(FIXTURES / "sample.jl")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)


def test_julia_no_dangling_edges():
    r = extract_julia(FIXTURES / "sample.jl")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"Dangling source: {e}"


# ── Fortran extractor ────────────────────────────────────────────────────────

def test_fortran_finds_module():
    r = extract_fortran(FIXTURES / "sample.f90")
    assert "error" not in r
    labels = [n["label"] for n in r["nodes"]]
    assert "geometry" in labels


def test_fortran_finds_subroutines():
    r = extract_fortran(FIXTURES / "sample.f90")
    labels = [n["label"] for n in r["nodes"]]
    assert any("circle_area" in l for l in labels)
    assert any("print_area" in l for l in labels)


def test_fortran_finds_function():
    r = extract_fortran(FIXTURES / "sample.f90")
    labels = [n["label"] for n in r["nodes"]]
    assert any("distance" in l for l in labels)


def test_fortran_finds_program():
    r = extract_fortran(FIXTURES / "sample.f90")
    labels = [n["label"] for n in r["nodes"]]
    assert "main" in labels


def test_fortran_finds_use_imports():
    r = extract_fortran(FIXTURES / "sample.f90")
    import_edges = [e for e in r["edges"] if e["relation"] == "imports"]
    assert len(import_edges) >= 2


def test_fortran_use_edges_have_use_context():
    r = extract_fortran(FIXTURES / "sample.f90")
    import_edges = [e for e in r["edges"] if e["relation"] == "imports"]
    assert all(e.get("context") == "use" for e in import_edges)


def test_fortran_finds_calls():
    r = extract_fortran(FIXTURES / "sample.f90")
    call_edges = [e for e in r["edges"] if e["relation"] == "calls"]
    assert len(call_edges) >= 1


def test_fortran_case_insensitive_names():
    r = extract_fortran(FIXTURES / "sample.f90")
    labels = [n["label"] for n in r["nodes"]]
    assert all(l == l.lower() or "(" in l for l in labels if l.endswith(("()", "")) and not "." in l)
    assert "geometry" in labels
    assert "main" in labels


def test_fortran_finds_derived_type():
    r = extract_fortran(FIXTURES / "sample.f90")
    labels = [n["label"] for n in r["nodes"]]
    assert "point" in labels


def test_fortran_parameter_and_return_type_contexts():
    r = extract_fortran(FIXTURES / "sample.f90")
    assert ("translate", "point") in _edge_labels(r, "references", "parameter_type")
    assert ("origin", "point") in _edge_labels(r, "references", "return_type")


def test_fortran_no_dangling_edges():
    r = extract_fortran(FIXTURES / "sample.f90")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"Dangling source: {e}"


def test_fortran_capital_F_parses_preprocessed():
    r = extract_fortran(FIXTURES / "sample_preprocessed.F90")
    assert "error" not in r
    labels = [n["label"] for n in r["nodes"]]
    assert "shapes" in labels
    assert any("compute_volume" in l for l in labels)


# ── PowerShell ───────────────────────────────────────────────────────────────

def test_powershell_no_error():
    r = extract_powershell(FIXTURES / "sample.ps1")
    assert "error" not in r


def test_powershell_psm1_dispatched_and_extracted(tmp_path):
    # #1315: .psm1 modules were never indexed — no dispatch entry, no CODE_EXTENSIONS.
    from graphify.extract import _get_extractor
    mod = tmp_path / "Utils.psm1"
    mod.write_text(
        "function Get-Greeting { param([string]$Name) return \"Hi $Name\" }\n",
        encoding="utf-8",
    )
    assert _get_extractor(mod) is extract_powershell
    r = extract_powershell(mod)
    assert "error" not in r
    assert any("Get-Greeting" in n["label"] for n in r["nodes"])


def test_powershell_finds_class_and_method():
    r = extract_powershell(FIXTURES / "sample.ps1")
    labels = [n["label"] for n in r["nodes"]]
    assert "DataProcessor" in labels
    assert any("Transform" in l for l in labels)


def test_powershell_property_field_type_context():
    r = extract_powershell(FIXTURES / "sample.ps1")
    assert ("DataProcessor", "string") in _edge_labels(r, "references", "field")


def test_powershell_method_parameter_and_return_type_contexts():
    r = extract_powershell(FIXTURES / "sample.ps1")
    assert ("Transform", "string") in _edge_labels(r, "references", "parameter_type")
    assert ("Transform", "string") in _edge_labels(r, "references", "return_type")
    assert ("Save", "void") in _edge_labels(r, "references", "return_type")


# ── PowerShell: Import-Module + dot-source (#1331) ───────────────────────────

def test_powershell_import_module_emits_edge():
    """Import-Module Foo at top level emits an imports_from edge."""
    r = extract_powershell(FIXTURES / "sample_import.ps1")
    assert "error" not in r
    targets = {e["target"] for e in r["edges"] if e["relation"] == "imports_from"}
    assert any("foo" in t for t in targets), f"Missing Import-Module Foo edge; targets={targets}"


def test_powershell_import_module_with_name_param():
    """Import-Module -Name Bar.psm1 resolves to module stem 'bar'."""
    r = extract_powershell(FIXTURES / "sample_import.ps1")
    targets = {e["target"] for e in r["edges"] if e["relation"] == "imports_from"}
    assert any("bar" in t for t in targets), f"Missing Import-Module -Name Bar edge; targets={targets}"


def test_powershell_dot_source_forward_slash_emits_edge():
    """Dot-source `. ./Shared.psm1` emits an imports_from edge."""
    r = extract_powershell(FIXTURES / "sample_import.ps1")
    targets = {e["target"] for e in r["edges"] if e["relation"] == "imports_from"}
    assert any("shared" in t for t in targets), f"Missing dot-source Shared edge; targets={targets}"


def test_powershell_dot_source_backslash_emits_edge():
    """Dot-source `. .\\Utils.ps1` (backslash path) emits an imports_from edge."""
    r = extract_powershell(FIXTURES / "sample_import.ps1")
    targets = {e["target"] for e in r["edges"] if e["relation"] == "imports_from"}
    assert any("utils" in t for t in targets), f"Missing dot-source Utils edge; targets={targets}"


def test_powershell_import_module_inside_function_emits_edge():
    """Import-Module inside a function body still produces an imports_from edge."""
    r = extract_powershell(FIXTURES / "sample_import.ps1")
    targets = {e["target"] for e in r["edges"] if e["relation"] == "imports_from"}
    assert any("innermod" in t for t in targets), (
        f"Missing Import-Module InnerMod edge from function body; targets={targets}"
    )


def test_powershell_import_module_not_a_raw_call():
    """Import-Module must not appear in raw_calls (it is an import, not a function call)."""
    r = extract_powershell(FIXTURES / "sample_import.ps1")
    import_module_calls = [
        rc for rc in r.get("raw_calls", [])
        if rc.get("callee", "").lower() == "import-module"
    ]
    assert not import_module_calls, (
        f"Import-Module appeared in raw_calls but should be emitted as import edge: {import_module_calls}"
    )


def test_powershell_dot_source_inside_function_emits_edge():
    """Dot-source inside a function body still produces an imports_from edge."""
    r = extract_powershell(FIXTURES / "sample_import.ps1")
    targets = {e["target"] for e in r["edges"] if e["relation"] == "imports_from"}
    assert any("innershared" in t for t in targets), (
        f"Missing dot-source InnerShared edge from function body; targets={targets}"
    )


# ── PowerShell manifest (.psd1) (#1331) ──────────────────────────────────────

def test_powershell_psd1_dispatched():
    """_get_extractor should route .psd1 to extract_powershell_manifest."""
    from graphify.extract import _get_extractor
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".psd1", delete=False) as f:
        f.write(b"@{ RootModule = 'X.psm1' }")
        path = f.name
    try:
        assert _get_extractor(Path(path)) is extract_powershell_manifest
    finally:
        os.unlink(path)


def test_powershell_psd1_no_error():
    r = extract_powershell_manifest(FIXTURES / "sample.psd1")
    assert "error" not in r


def test_powershell_psd1_has_file_node():
    r = extract_powershell_manifest(FIXTURES / "sample.psd1")
    assert any("sample.psd1" in n["label"] for n in r["nodes"]), (
        f"Missing file node for sample.psd1; nodes={[n['label'] for n in r['nodes']]}"
    )


def test_powershell_psd1_root_module():
    """RootModule = 'MyModule.psm1' produces an imports_from edge to 'mymodule'."""
    r = extract_powershell_manifest(FIXTURES / "sample.psd1")
    targets = {e["target"] for e in r["edges"] if e["relation"] == "imports_from"}
    assert any("mymodule" in t for t in targets), (
        f"Missing RootModule edge for MyModule; targets={targets}"
    )


def test_powershell_psd1_nested_modules():
    """NestedModules = @('Helpers.psm1', 'Logger.psm1') produces edges for both."""
    r = extract_powershell_manifest(FIXTURES / "sample.psd1")
    targets = {e["target"] for e in r["edges"] if e["relation"] == "imports_from"}
    assert any("helpers" in t for t in targets), f"Missing NestedModules Helpers edge; targets={targets}"
    assert any("logger" in t for t in targets), f"Missing NestedModules Logger edge; targets={targets}"


def test_powershell_psd1_required_modules_string():
    """RequiredModules string form 'PSReadLine' produces an imports_from edge."""
    r = extract_powershell_manifest(FIXTURES / "sample.psd1")
    targets = {e["target"] for e in r["edges"] if e["relation"] == "imports_from"}
    assert any("psreadline" in t for t in targets), (
        f"Missing RequiredModules PSReadLine edge; targets={targets}"
    )


def test_powershell_psd1_required_modules_hashtable():
    """RequiredModules hashtable form @{{ ModuleName='Pester' }} produces an imports_from edge."""
    r = extract_powershell_manifest(FIXTURES / "sample.psd1")
    targets = {e["target"] for e in r["edges"] if e["relation"] == "imports_from"}
    assert any("pester" in t for t in targets), (
        f"Missing RequiredModules Pester (hashtable form) edge; targets={targets}"
    )


def test_powershell_psd1_no_moduleversion_as_edge():
    """ModuleVersion values ('5.0', '1.0.0') must NOT appear as import targets."""
    r = extract_powershell_manifest(FIXTURES / "sample.psd1")
    targets = {e["target"] for e in r["edges"] if e["relation"] == "imports_from"}
    assert not any(t in targets for t in ("5_0", "1_0_0", "5.0", "1.0.0")), (
        f"ModuleVersion string leaked into import targets: {targets}"
    )


def test_powershell_psd1_no_dangling_edges():
    """All imports_from edge sources must exist in the node set."""
    r = extract_powershell_manifest(FIXTURES / "sample.psd1")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"Dangling source in edge: {e}"


# ── TypeScript dynamic imports ───────────────────────────────────────────────

def test_ts_dynamic_import_no_error():
    r = extract_js(FIXTURES / "dynamic_import.ts")
    assert "error" not in r

def test_ts_dynamic_import_extracts_edges():
    """Dynamic import() calls inside functions should produce imports_from edges."""
    r = extract_js(FIXTURES / "dynamic_import.ts")
    dyn_edges = [e for e in r["edges"] if e["relation"] == "imports_from"]
    targets = {e["target"] for e in dyn_edges}
    # Should find: static ./logger, dynamic ./mayaEngine.js, dynamic ./queue.js
    assert any("logger" in t for t in targets), f"Missing static import of logger: {targets}"
    assert any("mayaengine" in t.lower() for t in targets), f"Missing dynamic import of mayaEngine: {targets}"
    assert any("queue" in t.lower() for t in targets), f"Missing dynamic import of queue: {targets}"

def test_ts_dynamic_import_confidence():
    """Dynamic imports should have EXTRACTED confidence (they are deterministic string literals)."""
    r = extract_js(FIXTURES / "dynamic_import.ts")
    dyn_edges = [e for e in r["edges"]
                 if e["relation"] == "imports_from"
                 and "mayaengine" in e["target"].lower()]
    assert len(dyn_edges) >= 1
    assert dyn_edges[0]["confidence"] == "EXTRACTED"

def test_ts_dynamic_import_source_is_function():
    """Dynamic import edge source should be the enclosing function, not the file."""
    r = extract_js(FIXTURES / "dynamic_import.ts")
    node_labels = {n["id"]: n["label"] for n in r["nodes"]}
    dyn_edges = [e for e in r["edges"]
                 if e["relation"] == "imports_from"
                 and "mayaengine" in e["target"].lower()]
    assert len(dyn_edges) >= 1
    src_label = node_labels.get(dyn_edges[0]["source"], "")
    assert "processInbound" in src_label, f"Expected processInbound as source, got {src_label}"

def test_ts_no_dynamic_import_in_sync_fn():
    """Functions without dynamic imports should not get spurious imports_from edges."""
    r = extract_js(FIXTURES / "dynamic_import.ts")
    node_ids = {n["label"]: n["id"] for n in r["nodes"]}
    sync_nid = node_ids.get("syncOnly()")
    if sync_nid:
        sync_imports = [e for e in r["edges"]
                        if e["source"] == sync_nid and e["relation"] == "imports_from"]
        assert len(sync_imports) == 0

def test_ts_dynamic_template_literal_skipped():
    """Dynamic template literals (with ${}) must not produce an imports_from edge."""
    r = extract_js(FIXTURES / "dynamic_import.ts")
    targets = {e["target"] for e in r["edges"] if e["relation"] == "imports_from"}
    # loadHandler uses `./handlers/${handlerName}` — no static path, must be absent
    assert not any("handler" in t.lower() and "$" in t for t in targets), \
        f"Garbage edge from dynamic template literal found: {targets}"
    # More robust: no target should contain a brace character
    assert not any("{" in t or "}" in t for t in targets), \
        f"Target contains unresolved template expression: {targets}"

def test_ts_static_template_literal_resolved():
    """Static template literals (no ${}) should resolve the same as a plain string."""
    r = extract_js(FIXTURES / "dynamic_import.ts")
    targets = {e["target"] for e in r["edges"] if e["relation"] == "imports_from"}
    assert any("statichelper" in t.lower() for t in targets), \
        f"Static template literal import not resolved: {targets}"


def test_js_local_const_does_not_emit_phantom_node(tmp_path):
    """Local const/let/var inside an arrow callback must NOT emit a node (#1077).

    Previously `_js_extra_walk` recursed into arrow_function bodies and
    emitted a node for every `const x = ...` inside e.g. `describe(() => {})`,
    so bare names like `set`, `sorted` collided across unrelated test files.
    """
    src = (
        "describe('suite', () => {\n"
        "  const inner = new Set([1, 2, 3]);\n"
        "  let other = [1, 2];\n"
        "});\n"
        "\n"
        "const moduleConst = new Set([4, 5]);\n"
        "export const exportedConst = { a: 1 };\n"
    )
    f = tmp_path / "scope_guard.js"
    f.write_text(src)
    r = extract_js(f)
    labels = _labels(r)

    # Locals inside the arrow callback must not produce nodes.
    assert "inner" not in labels, f"phantom node for arrow-body local 'inner': {labels}"
    assert "other" not in labels, f"phantom node for arrow-body local 'other': {labels}"

    # Module-level consts should still produce nodes.
    assert "moduleConst" in labels, f"module-level const 'moduleConst' missing: {labels}"
    assert "exportedConst" in labels, f"exported const 'exportedConst' missing: {labels}"


def test_js_module_level_arrow_produces_node_and_call_edges(tmp_path):
    """Module-level arrow functions must still emit a node and capture their calls (#1077).

    The scope guard must not accidentally suppress top-level arrow functions.
    """
    src = (
        "function helper() { return 1; }\n"
        "const handler = () => {\n"
        "  helper();\n"
        "};\n"
    )
    f = tmp_path / "arrows.js"
    f.write_text(src)
    r = extract_js(f)
    labels = _labels(r)
    relations = _relations(r)

    assert any("handler" in l for l in labels), f"module-level arrow 'handler' missing: {labels}"
    assert "calls" in relations, f"expected 'calls' edge from handler->helper: {relations}"


def test_ts_local_const_does_not_emit_phantom_node(tmp_path):
    """Scope guard applies to TypeScript files too (shared _js_extra_walk path)."""
    src = (
        "describe('suite', () => {\n"
        "  const inner: Set<number> = new Set([1, 2]);\n"
        "});\n"
        "\n"
        "export const topLevel = { a: 1 };\n"
    )
    f = tmp_path / "scope_guard.ts"
    f.write_text(src)
    r = extract_js(f)
    labels = _labels(r)

    assert "inner" not in labels, f"phantom TS node for arrow-body local 'inner': {labels}"
    assert "topLevel" in labels, f"module-level TS const 'topLevel' missing: {labels}"


# ── Markdown ─────────────────────────────────────────────────────────────────

from graphify.extract import extract_markdown

def test_markdown_no_error():
    r = extract_markdown(FIXTURES / "deploy_guide.md")
    assert "error" not in r

def test_markdown_finds_headings():
    r = extract_markdown(FIXTURES / "deploy_guide.md")
    labels = _labels(r)
    assert any("Deploy Guide" in l for l in labels)
    assert any("Prerequisites" in l for l in labels)
    assert any("Full Deploy" in l for l in labels)
    assert any("Rollback" in l for l in labels)

def test_markdown_finds_nested_heading():
    """### Database Migration is nested under ## Full Deploy."""
    r = extract_markdown(FIXTURES / "deploy_guide.md")
    labels = _labels(r)
    assert any("Database Migration" in l for l in labels)

def test_markdown_skips_fenced_code_blocks():
    """Fenced code blocks should NOT emit nodes (#1077).

    They were always orphans (single contains edge to parent doc) and
    inflated the disconnected-component count. We still skip over their
    *contents* when parsing so the inside of a fence is not misread as a
    heading.
    """
    r = extract_markdown(FIXTURES / "deploy_guide.md")
    labels = _labels(r)
    assert not any(l.startswith("code:") for l in labels), \
        f"Expected no code:* nodes after #1077 fix, got: {[l for l in labels if l.startswith('code:')]}"

def test_markdown_contains_edges():
    """Headings should be connected via 'contains' edges (file->h, h->h)."""
    r = extract_markdown(FIXTURES / "deploy_guide.md")
    assert "contains" in _relations(r)
    contains_edges = [e for e in r["edges"] if e["relation"] == "contains"]
    # deploy_guide.md has: file->h1, h1->h2(Prerequisites), h1->h2(Full Deploy),
    # h2(Full Deploy)->h3(Database Migration), h1->h2(Rollback) = 5 edges
    assert len(contains_edges) >= 5, f"expected >= 5 contains edges, got {len(contains_edges)}"


def test_markdown_fenced_heading_not_parsed():
    """A '## heading' inside a fenced block must not produce a heading node (#1077).

    The fence-toggle skips over fenced contents so interior markdown syntax
    is not misread as document structure.
    """
    import tempfile, os
    src = (
        "# Real Heading\n"
        "\n"
        "```bash\n"
        "## Not A Heading\n"
        "echo hello\n"
        "```\n"
        "\n"
        "## Another Real Heading\n"
    )
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as fh:
        fh.write(src)
        fpath = fh.name
    try:
        r = extract_markdown(Path(fpath))
        labels = _labels(r)
    finally:
        os.unlink(fpath)

    assert any("Real Heading" in l for l in labels), f"'Real Heading' missing: {labels}"
    assert any("Another Real Heading" in l for l in labels), f"'Another Real Heading' missing: {labels}"
    assert not any("Not A Heading" in l for l in labels), \
        f"fenced '## Not A Heading' was incorrectly parsed as a node: {labels}"

def test_markdown_no_dangling_edges():
    r = extract_markdown(FIXTURES / "deploy_guide.md")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"Dangling source: {e}"


def _md_link_fixture(tmp_path):
    """A hub doc linking to sibling docs, plus those docs (#1376)."""
    pkg = tmp_path / "packages" / "coding-standards-csharp"
    pkg.mkdir(parents=True)
    (pkg / "index.md").write_text(
        "# C# Coding Standards\n\n"
        "| Topic | Doc |\n| --- | --- |\n"
        "| Repository | [C# Repository Standards](./repository.md) |\n"
        "| HTTP Client | [C# HTTP Client Standards](http-client.md) |\n"
        "| Unit Tests | [C# Unit Test Standards](unit-tests.md) |\n\n"
        "See also [external](https://example.com/x) and ![logo](./logo.png).\n"
        "Anchor: [section](./repository.md#setup).\n"
        "Wikilink: [[http-client]].\n"
    )
    (pkg / "repository.md").write_text("# C# Repository Standards\nContent.\n")
    (pkg / "http-client.md").write_text("# C# HTTP Client Standards\nContent.\n")
    (pkg / "unit-tests.md").write_text("# C# Unit Test Standards\nContent.\n")
    return pkg


def test_markdown_link_edges_emitted(tmp_path):
    """Inline/wikilink markdown links to sibling docs become references edges (#1376)."""
    pkg = _md_link_fixture(tmp_path)
    r = extract_markdown(pkg / "index.md")
    refs = [e for e in r["edges"] if e["relation"] == "references"]
    targets = {e["target"] for e in refs}
    # repository, http-client, unit-tests — each exactly once (deduped despite
    # the anchor link and wikilink pointing at repository/http-client again).
    assert len(refs) == 3, f"expected 3 reference edges, got {refs}"
    assert any("repository" in t for t in targets)
    assert any("http_client" in t for t in targets)
    assert any("unit_tests" in t for t in targets)


def test_markdown_link_skips_external_and_images(tmp_path):
    """External URLs, in-page anchors and images must not produce edges (#1376)."""
    pkg = _md_link_fixture(tmp_path)
    r = extract_markdown(pkg / "index.md")
    refs = [e for e in r["edges"] if e["relation"] == "references"]
    for e in refs:
        assert "example.com" not in e["target"]
        assert "logo" not in e["target"]


def test_markdown_link_edges_resolve_to_real_nodes(tmp_path):
    """End-to-end: after extract()'s ID remap, link targets are real doc nodes,
    so the hub doc gains edges into existing nodes instead of ghost nodes (#1376)."""
    from graphify.extract import extract
    pkg = _md_link_fixture(tmp_path)
    paths = sorted(pkg.glob("*.md"))
    res = extract(paths, cache_root=tmp_path, parallel=False)
    node_ids = {n["id"] for n in res["nodes"]}
    refs = [e for e in res["edges"] if e["relation"] == "references"]
    assert refs, "expected reference edges after full extract"
    for e in refs:
        assert e["target"] in node_ids, f"link target is a ghost node: {e}"
    # index.md must connect to all three sibling docs.
    index_id = next(n["id"] for n in res["nodes"] if n["label"] == "index.md")
    index_refs = {e["target"] for e in refs if e["source"] == index_id}
    assert len(index_refs) == 3, f"hub doc under-connected: {index_refs}"


# ── Groovy ───────────────────────────────────────────────────────────────────


def test_groovy_no_error():
    r = extract_groovy(FIXTURES / "sample.groovy")
    assert "error" not in r


def test_groovy_finds_class():
    r = extract_groovy(FIXTURES / "sample.groovy")
    assert any("SampleService" in l for l in _labels(r))


def test_groovy_finds_methods():
    r = extract_groovy(FIXTURES / "sample.groovy")
    labels = _labels(r)
    assert any("process" in l for l in labels)
    assert any("reset" in l for l in labels)


def test_groovy_finds_imports():
    r = extract_groovy(FIXTURES / "sample.groovy")
    assert "imports" in _relations(r)


def test_groovy_import_edges_have_import_context():
    r = extract_groovy(FIXTURES / "sample.groovy")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_groovy_no_dangling_edges():
    r = extract_groovy(FIXTURES / "sample.groovy")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids


def test_groovy_spock_finds_class():
    r = extract_groovy(FIXTURES / "sample_spock.groovy")
    assert any("SampleSpec" in l for l in _labels(r))


def test_groovy_spock_finds_feature_methods():
    r = extract_groovy(FIXTURES / "sample_spock.groovy")
    feature_labels = [l for l in _labels(r) if l.startswith('"')]
    assert len(feature_labels) >= 2


def test_groovy_spock_finds_method_with_apostrophe():
    r = extract_groovy(FIXTURES / "sample_spock.groovy")
    assert any("it's" in l for l in _labels(r))


def test_groovy_spock_preserves_import_edges():
    r = extract_groovy(FIXTURES / "sample_spock.groovy")
    assert "imports" in _relations(r)


def test_groovy_spock_no_dangling_edges():
    r = extract_groovy(FIXTURES / "sample_spock.groovy")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids


# ── DM (BYOND DreamMaker) ────────────────────────────────────────────────────

@_needs_dm
def test_dm_no_error():
    r = extract_dm(FIXTURES / "sample.dm")
    assert "error" not in r

@_needs_dm
def test_dm_finds_global_proc():
    r = extract_dm(FIXTURES / "sample.dm")
    labels = _labels(r)
    assert any(l == "log_event()" for l in labels)
    assert any(l == "RunTest()" for l in labels)

@_needs_dm
def test_dm_finds_type_definition():
    r = extract_dm(FIXTURES / "sample.dm")
    labels = _labels(r)
    assert "/datum/weapon" in labels
    assert "/datum/weapon/sword" in labels

@_needs_dm
def test_dm_qualifies_proc_with_type_path():
    r = extract_dm(FIXTURES / "sample.dm")
    labels = _labels(r)
    assert "/datum/weapon/attack()" in labels
    assert "/datum/weapon/sword/attack()" in labels

@_needs_dm
def test_dm_finds_path_form_proc_definition():
    r = extract_dm(FIXTURES / "sample.dm")
    assert "/datum/weapon/sword/sharpen()" in _labels(r)

@_needs_dm
def test_dm_emits_include_edge():
    r = extract_dm(FIXTURES / "sample.dm")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)

@_needs_dm
def test_dm_unresolved_include_flagged_external():
    r = extract_dm(FIXTURES / "sample.dm")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    helpers = [e for e in import_edges if "helpers" in e["target"]]
    assert helpers
    assert all(e.get("external") is True for e in helpers)

@_needs_dm
def test_dm_resolves_in_file_calls():
    r = extract_dm(FIXTURES / "sample.dm")
    calls = _calls(r)
    assert any(callee == "log_event()" for _, callee in calls)
    assert ("/datum/weapon/sword/attack()", "/datum/weapon/sword/sharpen()") in calls

@_needs_dm
def test_dm_ambiguous_member_call_left_unresolved():
    r = extract_dm(FIXTURES / "sample.dm")
    calls = _calls(r)
    runtest_to_attack = [c for s, c in calls
                         if s == "RunTest()" and "attack" in c]
    assert not runtest_to_attack
    assert any(rc["callee"] == "attack" for rc in r.get("raw_calls", []))

@_needs_dm
def test_dm_emits_new_as_instantiates():
    r = extract_dm(FIXTURES / "sample.dm")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    inst = [(node_by_id.get(e["source"]), node_by_id.get(e["target"]))
            for e in r["edges"] if e["relation"] == "instantiates"]
    assert ("RunTest()", "/datum/weapon/sword") in inst

@_needs_dm
def test_dm_call_edges_have_call_context():
    r = extract_dm(FIXTURES / "sample.dm")
    call_edges = _edges_with_relation(r, "calls", "instantiates")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)

@_needs_dm
def test_dm_no_dangling_edges():
    r = extract_dm(FIXTURES / "sample.dm")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids

@_needs_dm
def test_dm_super_call_not_emitted():
    r = extract_dm(FIXTURES / "sample.dm")
    calls = _calls(r)
    assert not any(callee.strip("()") == ".." for _, callee in calls)
    assert not any(rc["callee"] == ".." for rc in r.get("raw_calls", []))


# ── DMI (BYOND icon sheets) ──────────────────────────────────────────────────

def test_dmi_no_error():
    r = extract_dmi(FIXTURES / "sample.dmi")
    assert "error" not in r

def test_dmi_emits_state_nodes():
    r = extract_dmi(FIXTURES / "sample.dmi")
    labels = _labels(r)
    assert any(l == '"mob"' for l in labels)

def test_dmi_state_contained_by_file():
    r = extract_dmi(FIXTURES / "sample.dmi")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    contains = [(node_by_id.get(e["source"]), node_by_id.get(e["target"]))
                for e in r["edges"] if e["relation"] == "contains"]
    assert ("sample.dmi", '"mob"') in contains


# ── DMM (BYOND map files) ────────────────────────────────────────────────────

def test_dmm_no_error():
    r = extract_dmm(FIXTURES / "sample.dmm")
    assert "error" not in r

def test_dmm_extracts_type_paths_as_uses_edges():
    r = extract_dmm(FIXTURES / "sample.dmm")
    targets = {e["target"] for e in r["edges"] if e["relation"] == "uses"}
    assert "turf_closed_wall" in targets
    assert "obj_structure_table" in targets
    assert "obj_item_weapon_sword" in targets

def test_dmm_strips_var_overrides():
    r = extract_dmm(FIXTURES / "sample.dmm")
    targets = {e["target"] for e in r["edges"] if e["relation"] == "uses"}
    assert not any("{" in t for t in targets)
    assert "obj_item_weapon_sword" in targets

def test_dmm_handles_multiline_tile_definition():
    r = extract_dmm(FIXTURES / "sample.dmm")
    targets = {e["target"] for e in r["edges"] if e["relation"] == "uses"}
    assert "area_station_maintenance" in targets

def test_dmm_skips_grid_section():
    r = extract_dmm(FIXTURES / "sample.dmm")
    targets = {e["target"] for e in r["edges"] if e["relation"] == "uses"}
    assert len(targets) == 5


# ── DMF (BYOND interface forms) ──────────────────────────────────────────────

def test_dmf_no_error():
    r = extract_dmf(FIXTURES / "sample.dmf")
    assert "error" not in r

def test_dmf_extracts_windows():
    r = extract_dmf(FIXTURES / "sample.dmf")
    labels = _labels(r)
    assert 'window "mapwindow"' in labels
    assert 'window "infowindow"' in labels

def test_dmf_elem_labels_carry_control_type():
    r = extract_dmf(FIXTURES / "sample.dmf")
    labels = _labels(r)
    assert 'elem "map" [MAP]' in labels

def test_dmf_elem_under_window():
    r = extract_dmf(FIXTURES / "sample.dmf")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    contains = [(node_by_id.get(e["source"]), node_by_id.get(e["target"]))
                for e in r["edges"] if e["relation"] == "contains"]
    assert ('window "mapwindow"', 'elem "map" [MAP]') in contains

def test_dmf_no_dangling_edges():
    r = extract_dmf(FIXTURES / "sample.dmf")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids
        assert e["target"] in node_ids


# -- .NET project files (.sln, .csproj, .xaml, .razor) ------------------------

def test_sln_no_error():
    r = extract_sln(FIXTURES / "sample.sln")
    assert "error" not in r

def test_sln_finds_projects():
    r = extract_sln(FIXTURES / "sample.sln")
    labels = _labels(r)
    assert any("WebApi" in l for l in labels)
    assert any("Domain" in l for l in labels)

def test_sln_contains_edges():
    r = extract_sln(FIXTURES / "sample.sln")
    assert "contains" in _relations(r)

def test_sln_project_dependency_edges():
    r = extract_sln(FIXTURES / "sample.sln")
    assert "imports" in _relations(r)

def test_csproj_no_error():
    r = extract_csproj(FIXTURES / "sample.csproj")
    assert "error" not in r

def test_csproj_finds_packages():
    r = extract_csproj(FIXTURES / "sample.csproj")
    labels = _labels(r)
    assert any("MediatR" in l for l in labels)
    assert any("FluentValidation" in l for l in labels)

def test_csproj_finds_project_references():
    r = extract_csproj(FIXTURES / "sample.csproj")
    labels = _labels(r)
    assert any("Domain.csproj" in l for l in labels)

def test_csproj_finds_target_framework():
    r = extract_csproj(FIXTURES / "sample.csproj")
    assert any("net8.0" in l for l in _labels(r))

def test_csproj_finds_sdk():
    r = extract_csproj(FIXTURES / "sample.csproj")
    assert any("Microsoft.NET.Sdk.Web" in l for l in _labels(r))

def test_xaml_finds_class_and_event_references():
    r = extract_xaml(FIXTURES / "sample.xaml")
    assert "error" not in r
    assert "MainWindow" in _labels(r)
    assert any(e["relation"] == "references" and e.get("context") == "event" for e in r["edges"])

def test_razor_no_error():
    r = extract_razor(FIXTURES / "sample.razor")
    assert "error" not in r

def test_razor_finds_using_directives():
    r = extract_razor(FIXTURES / "sample.razor")
    assert "imports" in _relations(r)

def test_razor_finds_component_references():
    r = extract_razor(FIXTURES / "sample.razor")
    assert "calls" in _relations(r)

def test_razor_finds_inherits():
    r = extract_razor(FIXTURES / "sample.razor")
    assert "inherits" in _relations(r)

def test_razor_finds_code_block_methods():
    r = extract_razor(FIXTURES / "sample.razor")
    labels = _labels(r)
    assert any("IncrementCount" in l for l in labels)
    assert any("LoadData" in l for l in labels)

def test_razor_no_dangling_edges():
    r = extract_razor(FIXTURES / "sample.razor")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids


# ---------------Salesforce Apex (.cls / .trigger)----------------------

def test_apex_class_extraction():
    r = extract_apex(FIXTURES / "sample.cls")
    labels = _labels(r)
    assert "AccountService" in labels

def test_apex_enum_extraction():
    r = extract_apex(FIXTURES / "sample.cls")
    labels = _labels(r)
    assert "AccountStatus" in labels

def test_apex_interface_extraction():
    r = extract_apex(FIXTURES / "sample.cls")
    labels = _labels(r)
    assert "Notifiable" in labels

def test_apex_method_extraction():
    r = extract_apex(FIXTURES / "sample.cls")
    labels = _labels(r)
    assert any("getAccounts" in l for l in labels)
    assert any("updateAccountsAsync" in l for l in labels)
    assert any("createAccounts" in l for l in labels)
    assert any("deleteOldAccounts" in l for l in labels)

def test_apex_contains_and_method_relations():
    r = extract_apex(FIXTURES / "sample.cls")
    relations = _relations(r)
    assert "contains" in relations
    assert "method" in relations

def test_apex_soql_uses_edge():
    r = extract_apex(FIXTURES / "sample.cls")
    relations = _relations(r)
    assert "uses" in relations
    labels = _labels(r)
    assert "Account" in labels

def test_apex_dml_uses_edge():
    r = extract_apex(FIXTURES / "sample.cls")
    dml_labels = {n["label"] for n in r["nodes"] if n["label"] in ("insert", "update", "delete", "upsert")}
    assert len(dml_labels) > 0

def test_apex_file_node_present():
    r = extract_apex(FIXTURES / "sample.cls")
    labels = _labels(r)
    assert "sample.cls" in labels

def test_apex_trigger_extraction():
    r = extract_apex(FIXTURES / "sample.trigger")
    labels = _labels(r)
    assert "sample.trigger" in labels
    assert "AccountTrigger" in labels

def test_apex_trigger_uses_sobject():
    r = extract_apex(FIXTURES / "sample.trigger")
    relations = _relations(r)
    assert "uses" in relations
    labels = _labels(r)
    assert "Account" in labels

def test_apex_missing_file_returns_empty():
    r = extract_apex(Path("nonexistent.cls"))
    assert r["nodes"] == []
    assert r["edges"] == []

def test_apex_no_dangling_edges():
    for fixture in ("sample.cls", "sample.trigger"):
        r = extract_apex(FIXTURES / fixture)
        node_ids = {n["id"] for n in r["nodes"]}
        for e in r["edges"]:
            assert e["source"] in node_ids, f"dangling source in {fixture}: {e}"
            assert e["target"] in node_ids, f"dangling target in {fixture}: {e}"


# -- SystemVerilog -------------------------------------------------------------

def test_systemverilog_no_error():
    r = extract_verilog(FIXTURES / "sample.sv")
    assert "error" not in r


def test_systemverilog_splits_inherits_and_implements():
    r = extract_verilog(FIXTURES / "sample.sv")
    assert ("DataProcessor", "BaseProcessor") in _edge_labels(r, "inherits")
    assert ("DataProcessor", "Processor") in _edge_labels(r, "implements")


def test_systemverilog_field_parameter_return_and_generic_contexts():
    r = extract_verilog(FIXTURES / "sample.sv")
    assert ("DataProcessor", "Result") in _edge_labels(r, "references", "field")
    assert ("DataProcessor", "Payload") in _edge_labels(r, "references", "generic_arg")
    assert ("build", "Payload") in _edge_labels(r, "references", "parameter_type")
    assert ("build", "Result") in _edge_labels(r, "references", "return_type")
    assert ("build", "Payload") in _edge_labels(r, "references", "generic_arg")


def test_systemverilog_does_not_emit_type_parameter_refs():
    r = extract_verilog(FIXTURES / "sample.sv")
    assert ("Result", "T") not in _edge_labels(r, "references", "field")


def test_systemverilog_preserves_existing_module_extraction():
    r = extract_verilog(FIXTURES / "sample.sv")
    labels = set(_labels(r))
    assert {"top", "leaf", "add()", "tick"}.issubset(labels)
    assert "imports_from" in _relations(r)
    assert "instantiates" in _relations(r)


def test_systemverilog_missing_file_returns_empty():
    r = extract_verilog(Path("nonexistent.sv"))
    assert r["nodes"] == []
    assert r["edges"] == []


def test_systemverilog_no_dangling_edges():
    r = extract_verilog(FIXTURES / "sample.sv")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"dangling source: {e}"
        assert e["target"] in node_ids, f"dangling target: {e}"
