"""INC-QML-132: upstream case-only allocation retains native source authority."""
from __future__ import annotations

import copy
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.cache import load_cached
from graphify.extract import collect_files, extract, extract_cpp, extract_java, extract_kotlin
from graphify.extractors.cpp_functions import free_definition_fact
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from tests.test_qt_final_incremental_parity import normalized


TYPE = """class Foo : public QObject { Q_OBJECT QML_NAMED_ELEMENT(Service)
public: Q_INVOKABLE int value() { return 1; }
};
"""
FUNCTION = "int foo() { return 2; }\nint caller() { return foo(); }\n"


def generic_identities(result):
    """The actual generic allocator, not a same-label stub, owns each source role."""
    classes = [node for node in result["nodes"] if node.get("label") == "Foo"
               and node.get("_callable_class")]
    functions = {node["label"]: node for node in result["nodes"]
                 if free_definition_fact(node)}
    assert len(classes) == 1 and {"foo()", "caller()"} <= functions.keys()
    owner, function, caller = classes[0], functions["foo()"], functions["caller()"]
    assert len({owner["id"], function["id"], caller["id"]}) == 3
    assert all(node.get("source_file") and node.get("source_location")
               for node in (owner, function, caller))
    assert any(edge["source"] == caller["id"] and edge["target"] == function["id"]
               and edge["relation"] == "calls" for edge in result["edges"])
    assert not any(edge["source"] == caller["id"] and edge["target"] == owner["id"]
                   and edge["relation"] == "calls" for edge in result["edges"])
    return owner["id"], function["id"], caller["id"]


def native_call(graph, owner):
    """QML reaches only the member proven by the accepted canonical class."""
    calls = [(source, target, data) for source, target, data in graph.edges(data=True)
             if data.get("context") == "qml_js_call"]
    assert len(calls) == 1
    source, target, edge = calls[0]
    proof = qt_metadata(edge)["native_endpoint"]
    actual_target = edge.get("_tgt", target)
    assert proof["class_id"] == owner
    assert proof["canonical_target_id"] == actual_target
    assert graph.nodes[actual_target]["label"] == ".value()"
    assert graph.nodes[actual_target]["source_file"] == "native.cpp"
    return actual_target


@pytest.mark.parametrize("type_first", [True, False], ids=["type-first", "function-first"])
def test_req_qml010_ac01_ac02_ac03_req_qml022_ac02_ac06_case_only_roles_round_trip(
        tmp_path_factory, monkeypatch, type_first):
    """Direct, cold/warm and typed consumer paths preserve both generic and Qt identities.

    Upstream #4904 separates different-kind names after normalization. Qt must
    still map its native member to the actual allocated class in either source
    order; the lowercase free function cannot acquire QObject/provider authority.
    """
    # Keep the fixture root short independently of its acceptance-oriented name.
    tmp_path = tmp_path_factory.mktemp("up100")
    source = tmp_path / "native.cpp"
    source.write_text(TYPE + FUNCTION if type_first else FUNCTION + TYPE, encoding="utf-8")
    (tmp_path / "CMakeLists.txt").write_text(
        "qt_add_qml_module(app URI Public.Tools VERSION 1.0 "
        "QML_FILES Main.qml SOURCES native.cpp)\n", encoding="utf-8")
    (tmp_path / "Main.qml").write_text(
        "import Public.Tools 1.0\nService { property int observed: value() }\n",
        encoding="utf-8")
    retained = tmp_path / "keep.py"
    retained.write_text("def retained(): return 7\n", encoding="utf-8")
    direct = extract_cpp(source)
    assert not direct.get("parse_errors")
    generic_identities(direct)
    paths = collect_files(tmp_path, root=tmp_path)
    cold = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not cold["failed_sources"] and not cold.get("qml_failures")
    identities = generic_identities(cold)

    # Qt policy deliberately reparses native syntax in this mixed corpus. The
    # unrelated Python sibling must really warm-hit its raw-cache entry while
    # native enrichment keeps its accepted-source index and canonical mapping.
    import graphify.extract as extraction

    observed, real_extract = [], extraction._safe_extract_with_xaml_root

    def observe(extractor, path, root):
        observed.append(path)
        return real_extract(extractor, path, root)

    monkeypatch.setattr(extraction, "_safe_extract_with_xaml_root", observe)
    warm = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert source in observed and retained not in observed
    assert not warm["failed_sources"] and not warm.get("qml_failures")
    assert generic_identities(warm) == identities
    restored_graphs = []
    for name, facts in (("cold", cold), ("warm", warm)):
        graph = build_from_json(facts, root=tmp_path, directed=True)
        target = native_call(graph, identities[0])
        output = tmp_path / f"{name}.json"
        assert to_json(graph, {}, str(output), force=True)
        restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
        assert native_call(restored, identities[0]) == target
        assert restored.has_edge(identities[2], identities[1])
        assert restored[identities[2]][identities[1]]["relation"] == "calls"
        restored_graphs.append(restored)
    assert normalized(restored_graphs[0]) == normalized(restored_graphs[1])


@pytest.mark.parametrize("caller_suffix", ["kt", "java"], ids=["kotlin-caller", "java-caller"])
@pytest.mark.parametrize("provider_suffix", ["java", "kt"], ids=["java", "kotlin"])
@pytest.mark.parametrize("package_state", ["valid", "missing", "null", "wrong-type", "oversize",
                                          "malformed", "not-type", "duplicate"])
def test_req_core005_ac01_ac02_jvm_changed_caller_retains_written_package_with_accepted_context(
        tmp_path_factory, monkeypatch, provider_suffix, package_state, caller_suffix):
    """The caller's explicit FQN must select the same unchanged JVM definition.

    Two same-named accepted providers defeat generic basename guessing. Only
    fresh caller edges may be returned, and borrowed nodes/edges stay unchanged.
    """
    root = tmp_path_factory.mktemp("jvm100")
    paths = []
    provider_source = ("package {package};\npublic class Logger {{}}\n"
                       if provider_suffix == "java" else "package {package}\nopen class Logger\n")
    provider_names = {f"a/Logger.{provider_suffix}", f"b/Logger.{provider_suffix}"}
    caller_name = f"Use.{caller_suffix}"
    caller_source = ("package app;\nimport b.Logger;\npublic class Use extends Logger {}\n"
                     if caller_suffix == "java" else "package app\nimport b.Logger\nclass Use : Logger()\n")
    for relative, text in {
        f"a/Logger.{provider_suffix}": provider_source.format(package="a"),
        f"b/Logger.{provider_suffix}": provider_source.format(package="b"),
        caller_name: caller_source,
    }.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    complete = extract(paths, root=root, cache_root=root, parallel=False)
    expected = next(node["id"] for node in complete["nodes"]
                    if node.get("label") == "Logger"
                    and node.get("source_file") == f"b/Logger.{provider_suffix}")
    relations = {"imports", "inherits"}
    expected_edges = {(edge["source"], edge["target"], edge["relation"])
                      for edge in complete["edges"]
                      if edge.get("source_file") == caller_name and edge.get("relation") in relations}
    assert {relation for _, target, relation in expected_edges if target == expected} == relations
    graph = build_from_json(complete, root=root, directed=True)
    output = root / "accepted.json"
    assert to_json(graph, {}, str(output), force=True)
    accepted = json.loads(output.read_text(encoding="utf-8"))
    context_nodes = [node for node in accepted["nodes"]
                     if node.get("source_file") in provider_names]
    context_edges = [edge for edge in accepted["links"]
                     if edge.get("source_file") in provider_names]
    selected = next(node for node in context_nodes if node["id"] == expected)
    if package_state == "missing":
        selected["metadata"].pop("jvm_package")
    elif package_state in {"null", "wrong-type", "oversize", "malformed"}:
        selected["metadata"]["jvm_package"] = {
            "null": None, "wrong-type": ["b"], "oversize": "b" * 513, "malformed": "b..scope",
        }[package_state]
    elif package_state == "not-type":
        selected["_callable_class"] = False
    elif package_state == "duplicate":
        peer = copy.deepcopy(selected)
        peer["id"] += "_peer"
        context_nodes.append(peer)
    prior = copy.deepcopy((context_nodes, context_edges))
    # Accepted context is already source evidence, never permission to reopen
    # unchanged providers or manufacture another interpretation of the corpus.
    from pathlib import Path

    original_reads = {name: getattr(Path, name) for name in ("read_bytes", "read_text")}
    for name, original in original_reads.items():
        def read(path, *args, _original=original, **kwargs):
            assert path not in paths[:-1], f"borrowed provider reopened: {path}"
            return _original(path, *args, **kwargs)

        monkeypatch.setattr(Path, name, read)
    partial = extract([paths[-1]], root=root, cache_root=root, parallel=False,
                      resolution_context_nodes=context_nodes,
                      resolution_context_edges=context_edges)
    assert (context_nodes, context_edges) == prior
    actual_edges = {(edge["source"], edge["target"], edge["relation"])
                    for edge in partial["edges"]
                    if edge.get("source_file") == caller_name and edge.get("relation") in relations}
    if package_state == "valid":
        assert expected_edges <= actual_edges
    else:
        assert not any(target == expected for _, target, _ in actual_edges)
        file_ids = {node["id"] for node in context_nodes
                    if not node.get("_callable") and not node.get("_callable_class")}
        assert not any(target in file_ids and relation != "imports" for _, target, relation in actual_edges)
        if caller_suffix == "java":
            targets = {target for _, target, relation in actual_edges if relation == "inherits"}
            stubs = [node for node in partial["nodes"] if node["id"] in targets]
            assert targets and {node["id"] for node in stubs} == targets
            assert all(node.get("source_file") == "" and node["label"] == "b.Logger" for node in stubs)
            repeated = extract([paths[-1]], root=root, cache_root=root, parallel=False,
                               resolution_context_nodes=list(reversed(context_nodes)),
                               resolution_context_edges=list(reversed(context_edges)))
            assert {edge["target"] for edge in repeated["edges"] if edge.get("relation") == "inherits"} == targets
            assert (context_nodes, context_edges) == prior
    assert not any(node.get("source_file") in provider_names
                   for node in partial["nodes"])


@pytest.mark.parametrize("suffix,producer", [("java", extract_java), ("kt", extract_kotlin)], ids=["java", "kotlin"])
@pytest.mark.parametrize("package", ["", "one.two", "a" * 512], ids=["default", "named", "max"])
def test_req_core005_ac03_direct_producer_cache_export_preserve_exact_package(
        tmp_path_factory, suffix, producer, package):
    """Explicit default/named/boundary package evidence survives each production boundary."""
    root = tmp_path_factory.mktemp("jvmmark")
    path = root / f"Owner.{suffix}"
    header = f"package {package}" + (";\n" if suffix == "java" else "\n") if package else ""
    body = ('class Owner { String note = "package @"; }\n' if suffix == "java"
            else 'class Owner { val note = "package @" }\n')
    path.write_text("// package @\n" + header + body, encoding="utf-8")
    direct = producer(path)
    owner = next(node for node in direct["nodes"] if node.get("_callable_class"))
    assert owner["metadata"]["jvm_package"] == package
    assert all("jvm_package" not in node.get("metadata", {}) for node in direct["nodes"] if node is not owner)
    facts = extract([path], root=root, cache_root=root, parallel=False)
    cached = load_cached(path, root, cache_root=root)
    assert cached is not None
    assert next(node for node in cached["nodes"] if node.get("_callable_class"))["metadata"]["jvm_package"] == package
    output = root / "export.json"
    assert to_json(build_from_json(facts, root=root, directed=True), {}, str(output), force=True)
    exported = json.loads(output.read_text(encoding="utf-8"))
    assert next(node for node in exported["nodes"] if node.get("_callable_class"))["metadata"]["jvm_package"] == package


@pytest.mark.parametrize("suffix,producer", [("java", extract_java), ("kt", extract_kotlin)], ids=["java", "kotlin"])
@pytest.mark.parametrize("package", ["one..two", "a" * 513, "@"], ids=["malformed", "oversize", "recovered-header"])
def test_req_core005_ac02_malformed_or_oversize_source_package_cannot_become_default(
        tmp_path_factory, suffix, producer, package):
    """Partial syntax and over-limit spelling never acquire a truncated/default authority."""
    root = tmp_path_factory.mktemp("jvmbad")
    path = root / f"Owner.{suffix}"
    path.write_text(f"package {package}" + (";\n" if suffix == "java" else "\n")
                    + "class Owner {}\n", encoding="utf-8")
    result = producer(path)
    if package == "@" and suffix == "java":
        assert result.get("parse_errors") and any(node.get("_callable_class") for node in result["nodes"])
    assert not any("jvm_package" in node.get("metadata", {}) for node in result["nodes"])


@pytest.mark.parametrize("caller_suffix", ["kt", "java"], ids=["kotlin-caller", "java-caller"])
@pytest.mark.parametrize("package_state", ["wrong-package", "missing", "malformed"])
def test_req_core005_ac02_unique_same_name_provider_cannot_override_explicit_import(
        tmp_path_factory, package_state, caller_suffix):
    """A failed package lookup cannot fall back to a sole convenient same-name type."""
    root = tmp_path_factory.mktemp("jvmwrong")
    provider, caller = root / "Logger.java", root / f"Use.{caller_suffix}"
    package = "a" if package_state == "wrong-package" else "b"
    provider.write_text(f"package {package};\npublic class Logger {{}}\n", encoding="utf-8")
    caller_source = ("package app;\nimport b.Logger;\npublic class Use extends Logger {}\n"
                     if caller_suffix == "java" else "package app\nimport b.Logger\nclass Use : Logger()\n")
    caller.write_text(caller_source, encoding="utf-8")
    complete = extract([provider, caller], root=root, cache_root=root, parallel=False)
    chosen = next(node for node in complete["nodes"] if node.get("label") == "Logger" and node.get("source_file"))
    contexts = [copy.deepcopy(node) for node in complete["nodes"] if node.get("source_file") == "Logger.java"]
    for node in contexts:
        if node.get("_callable_class") and package_state == "missing":
            node["metadata"].pop("jvm_package")
        elif node.get("_callable_class") and package_state == "malformed":
            node["metadata"]["jvm_package"] = "b..scope"
    before = copy.deepcopy(contexts)
    partial = extract([caller], root=root, cache_root=root, parallel=False, resolution_context_nodes=contexts)
    assert contexts == before
    checks = [complete, partial] if package_state == "wrong-package" else [partial]
    for result in checks:
        assert not any(edge["target"] == chosen["id"] and edge["relation"] in {"imports", "inherits"}
                       for edge in result["edges"] if edge.get("source_file") == caller.name)
