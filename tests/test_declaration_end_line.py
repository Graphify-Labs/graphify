import copy
import json
from types import SimpleNamespace

import pytest

from graphify.build import build, prefix_graph_for_global
from graphify.export import to_json
from graphify.extract import _get_extractor, extract
from graphify.extractors.resolution import _merge_decl_def_classes


def _extract_file(path):
    extractor = _get_extractor(path)
    assert extractor is not None
    return extractor(path)


def _node(result, label):
    matches = [n for n in result["nodes"] if n["label"] == label]
    assert len(matches) == 1, matches
    return matches[0]


@pytest.mark.parametrize(
    "suffix, source, label, start, end",
    [
        ("py", "class Box:\n    def run(self):\n        pass\n", "Box", 1, 3),
        ("py", "def run(): return 1\n", "run()", 1, 1),
        ("py", "def run():\n    return 1\n\n# trailing\n", "run()", 1, 2),
        ("js", "const run = () => {\n  return 1;\n};\n", "run()", 1, 3),
        ("ts", "namespace Tools {\n  export const value = 1;\n}\n", "Tools", 1, 3),
        ("cs", "enum Color {\n Red = 1,\n Blue\n}\n", "Red", 2, 2),
        ("java", "enum Color {\n Red,\n Blue\n}\n", "Red", 2, 2),
        ("kt", "enum class Color {\n Red,\n Blue\n}\n", "Red", 2, 2),
        ("swift", "enum Color {\n case red\n case blue\n}\n", "red", 2, 2),
        ("scala", "enum Color:\n  case Red\n  case Blue\n", "Red", 2, 2),
        ("cpp", "enum Color {\n Red = 1,\n Blue\n};\n", "Red", 2, 2),
        ("cpp", "struct Box {\n int value =\n  1 +\n  2;\n};\n", "value", 2, 4),
        ("cpp", "struct Box {\n int\n value =\n  1;\n};\n", "value", 3, 4),
        ("cpp", "struct Box {\n int first =\n  1, second =\n  2;\n};\n", "first", 2, 3),
        ("cpp", "struct Box {\n int first =\n  1, second =\n  2;\n};\n", "second", 3, 4),
        ("cpp", "struct Box {\n virtual int run()\n = 0;\n};\n", ".run()", 2, 3),
        ("php", "<?php\nenum Color {\n case Red;\n}\n", "Red", 3, 3),
        ("go", "package p\nfunc run() {\n println(1)\n}\n", "run()", 2, 4),
        ("go", "package p\ntype Box struct {\n value int\n}\n", "Box", 2, 4),
        ("go", "package p\ntype Runner interface {\n Run(\n  value int,\n )\n}\n", ".Run()", 3, 5),
        ("m", "@implementation Box\n- (void)run {\n return;\n}\n@end\n", "-run", 2, 4),
        ("py", "class Box:\n    def run(self):\n        pass\n", ".run()", 2, 3),
        ("py", "def outer():\n    def inner():\n        pass\n", "inner()", 2, 3),
        ("js", "const first = () => 1, second = () => {\n return 2;\n};\n", "first()", 1, 1),
        ("js", "function outer() {\n function inner() {\n }\n}\n", "inner()", 2, 3),
        ("cs", "class Box {\n public int Value {\n get; set;\n }\n}\n", "Value", 2, 4),
        ("c", "int run(void) {\n return 1;\n}\n", "run()", 1, 3),
        ("rb", "class Box\n def run\n  1\n end\nend\n", ".run()", 2, 4),
        ("lua", "function run()\n return 1\nend\n", "run()", 1, 3),
        ("go", "package p\nfunc run() {}\n", "run()", 2, 2),
    ],
)
def test_declaration_ranges(tmp_path, suffix, source, label, start, end):
    path = tmp_path / f"sample.{suffix}"
    path.write_text(source, encoding="utf-8")
    result = _extract_file(path)
    assert not result.get("error"), result
    node = _node(result, label)
    assert node["source_file"] == str(path)
    assert node["source_location"] == f"L{start}"
    assert node.get("source_end_location") == f"L{end}", node
    for other in result["nodes"]:
        if other["label"] == path.name or not other.get("source_file"):
            assert "source_end_location" not in other, other


@pytest.mark.parametrize("end_point, expected", [((4, 0), 4), ((4, 3), 5), ((0, 5), 1)])
def test_exclusive_end_point(end_point, expected):
    from graphify.extractors.base import _inclusive_end_line

    ast_node = SimpleNamespace(start_point=(0, 0), end_point=end_point)
    assert _inclusive_end_line(ast_node) == expected


def test_go_interface_marker_preserves_range(tmp_path):
    path = tmp_path / "sample.go"
    path.write_text("package p\ntype Runner interface {\n Run()\n}\n", encoding="utf-8")
    node = _node(_extract_file(path), "Runner")
    assert node["source_location"] == "L2"
    assert node["metadata"] == {"language": "go", "kind": "interface"}
    assert node["source_end_location"] == "L4"


def test_go_receiver_owner_has_no_range_and_real_type_wins(tmp_path):
    path = tmp_path / "sample.go"
    path.write_text(
        "package p\nfunc (b Box) Run() {\n}\ntype Box struct {\n value int\n}\n",
        encoding="utf-8",
    )
    result = _extract_file(path)
    method = _node(result, ".Run()")
    assert method.get("source_end_location") == "L3"
    owner = _node(result, "Box")
    assert owner["source_location"] == "L4"
    assert owner.get("source_end_location") == "L6"
    path.write_text("package p\nfunc (b Foreign) Run() {}\n", encoding="utf-8")
    owner = _node(_extract_file(path), "Foreign")
    assert "source_end_location" not in owner


def test_objc_declaration_and_definition_ranges_survive_pipeline(tmp_path, monkeypatch):
    header = tmp_path / "Box.h"
    impl = tmp_path / "Box.m"
    header.write_text("@interface Box\n- (void)run;\n@end\n", encoding="utf-8")
    impl.write_text(
        '#import "Box.h"\n\n@implementation Box\n- (void)run {\n return;\n}\n@end\n',
        encoding="utf-8",
    )
    result = extract([impl, header], root=tmp_path, cache_root=tmp_path, parallel=False)
    for label, source_start, source_end, def_start, def_end in [
        ("Box", 1, 3, 3, 7), ("-run", 2, 2, 4, 6),
    ]:
        node = _node(result, label)
        assert node["source_file"] == "Box.h"
        assert node["source_location"] == f"L{source_start}"
        assert node["definition_file"] == "Box.m"
        assert node["definition_location"] == f"L{def_start}"
        assert node.get("source_end_location") == f"L{source_end}"
        assert node.get("definition_end_location") == f"L{def_end}"
    before = copy.deepcopy(result)
    _merge_decl_def_classes(result["nodes"], result["edges"])
    assert result == before
    graph = build([result, copy.deepcopy(result)], root=tmp_path)
    prefixed = prefix_graph_for_global(graph, "example")
    for node in result["nodes"]:
        if node["label"] in {"Box", "-run"}:
            for key in ("source_end_location", "definition_end_location"):
                assert graph.nodes[node["id"]][key] == node[key]
                assert prefixed.nodes[f"example::{node['id']}"][key] == node[key]
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output))
    saved = json.loads(output.read_text())
    assert _node(saved, "-run")["definition_end_location"] == "L6"
    import graphify.global_graph as global_graph

    global_dir = tmp_path / "global"
    monkeypatch.setattr(global_graph, "_GLOBAL_DIR", global_dir)
    monkeypatch.setattr(global_graph, "_GLOBAL_GRAPH", global_dir / "graph.json")
    monkeypatch.setattr(global_graph, "_GLOBAL_MANIFEST", global_dir / "manifest.json")
    global_graph.global_add(output, "example")
    stored = global_graph._load_global_graph()
    method_id = _node(result, "-run")["id"]
    assert stored.nodes[f"example::{method_id}"]["definition_end_location"] == "L6"


@pytest.mark.parametrize("reverse", [False, True])
def test_objc_extension_definition_ranges_survive_header_merge(tmp_path, reverse):
    header = tmp_path / "Box.h"
    impl = tmp_path / "Box.m"
    header.write_text("@interface Box\n- (void)run;\n@end\n", encoding="utf-8")
    impl.write_text(
        '#import "Box.h"\n@interface Box ()\n- (void)run;\n@end\n'
        "@implementation Box\n- (void)run {\n return;\n}\n@end\n",
        encoding="utf-8",
    )
    paths = [header, impl] if reverse else [impl, header]
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    for label, source_start, source_end, definition_start, definition_end in [
        ("Box", 1, 3, 5, 9), ("-run", 2, 2, 6, 8),
    ]:
        node = _node(result, label)
        assert node["source_file"] == "Box.h"
        assert node["source_location"] == f"L{source_start}"
        assert node["source_end_location"] == f"L{source_end}"
        assert node["definition_file"] == "Box.m"
        assert node["definition_location"] == f"L{definition_start}"
        assert node["definition_end_location"] == f"L{definition_end}"
    before = copy.deepcopy(result)
    _merge_decl_def_classes(result["nodes"], result["edges"])
    assert result == before


@pytest.mark.parametrize("reverse", [False, True])
def test_duplicate_merge_fills_range_only_for_matching_location(reverse):
    from graphify.dedup import _merge_missing_attributes

    keeper = {"source_file": "sample.py", "source_location": "L2", "metadata": {"kind": "fn"}}
    same = {"source_file": "sample.py", "source_location": "L2", "source_end_location": "L4"}
    first, second = (same, keeper) if reverse else (keeper, same)
    merged = _merge_missing_attributes(first, second)
    assert merged["source_end_location"] == "L4"
    assert first == (same if reverse else keeper)
    different = {**same, "source_location": "L8"}
    assert "source_end_location" not in _merge_missing_attributes(keeper, different)
    no_location = {k: v for k, v in keeper.items() if k != "source_location"}
    other_file = {**same, "source_file": "other.py"}
    assert "source_end_location" not in _merge_missing_attributes(no_location, other_file)


def test_objc_same_file_keeps_both_sites(tmp_path):
    path = tmp_path / "Box.m"
    path.write_text(
        "@interface Box\n- (void)run;\n@end\n"
        "@implementation Box\n- (void)run {\n return;\n}\n@end\n",
        encoding="utf-8",
    )
    result = _extract_file(path)
    for label, source_end, definition_start, definition_end in [
        ("Box", 3, 4, 8), ("-run", 2, 5, 7),
    ]:
        node = _node(result, label)
        assert node["source_end_location"] == f"L{source_end}"
        assert node.get("definition_file") == str(path)
        assert node.get("definition_location") == f"L{definition_start}"
        assert node.get("definition_end_location") == f"L{definition_end}"


def test_objc_enum_uses_original_declaration(tmp_path):
    path = tmp_path / "Colors.m"
    path.write_text(
        "typedef enum {\n Red = 1,\n Blue\n}\nColor;\n",
        encoding="utf-8",
    )
    from graphify.extractors.objc import extract_objc

    result = extract_objc(path)
    enum = _node(result, "Color")
    assert enum["source_location"] == "L1"
    assert enum.get("source_end_location") == "L5"
    assert _node(result, "Red").get("source_end_location") == "L2"


def test_cached_extraction_retains_ranges(tmp_path):
    path = tmp_path / "sample.py"
    path.write_text("def run():\n    return 1\n", encoding="utf-8")
    first = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    second = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert _node(first, "run()")["source_end_location"] == "L2"
    assert _node(second, "run()") == _node(first, "run()")


def test_previous_schema_cache_is_retired(tmp_path, monkeypatch):
    import graphify.cache as cache

    path = tmp_path / "sample.py"
    path.write_text("def run():\n    return 1\n", encoding="utf-8")
    current_schema = cache._AST_CACHE_SCHEMA
    monkeypatch.setattr(cache, "_AST_CACHE_SCHEMA", current_schema - 1)
    cache.save_cached(path, {"nodes": [], "edges": []}, root=tmp_path, kind="ast")
    monkeypatch.setattr(cache, "_AST_CACHE_SCHEMA", current_schema)
    assert cache.load_cached(path, root=tmp_path, kind="ast") is None


@pytest.mark.parametrize("reverse", [False, True])
def test_build_duplicate_preserves_range_with_existing_metadata(reverse):
    complete = {
        "id": "run", "label": "run()", "source_file": "sample.py",
        "source_location": "L2", "file_type": "code", "source_end_location": "L4",
    }
    duplicate = {k: v for k, v in complete.items() if k != "source_end_location"}
    duplicate["metadata"] = {"kind": "function", "arity": 0}
    nodes = [complete, duplicate]
    if reverse:
        nodes.reverse()
    graph = build([{"nodes": nodes, "edges": []}])
    assert graph.nodes["run"]["source_end_location"] == "L4"
    assert "metadata" not in complete


@pytest.mark.parametrize("header_has_definition", [False, True])
@pytest.mark.parametrize("known_end", [False, True])
def test_definition_merge_uses_explicit_implementation_site(header_has_definition, known_end):
    header = {
        "id": "box", "label": "Box", "file_type": "code", "source_file": "Box.h",
        "source_location": "L1", "source_end_location": "L3",
    }
    if header_has_definition:
        header.update(definition_file="Box.m", definition_location="L8", definition_end_location="L12")
    impl = {
        **header, "source_file": "Box.m", "source_location": "L2", "source_end_location": "L4",
        "definition_file": "Box.m", "definition_location": "L5",
    }
    impl.pop("definition_end_location", None)
    if known_end:
        impl["definition_end_location"] = "L9"
    nodes = [header, impl]
    _merge_decl_def_classes(nodes, [])
    assert nodes == [header]
    assert header["source_file"] == "Box.h"
    assert header["source_location"] == "L1"
    assert header["source_end_location"] == "L3"
    assert header["definition_file"] == "Box.m"
    assert header["definition_location"] == "L5"
    assert header.get("definition_end_location") == ("L9" if known_end else None)
    before = copy.deepcopy(header)
    _merge_decl_def_classes(nodes, [])
    assert header == before


@pytest.mark.parametrize("reverse", [False, True])
def test_definition_merge_keeps_separate_ranges(reverse):
    header = {
        "id": "box", "label": "Box", "file_type": "code", "source_file": "Box.h",
        "source_location": "L1", "source_end_location": "L3",
    }
    impl = {
        **header, "source_file": "Box.m", "source_location": "L10",
        "source_end_location": "L20",
    }
    nodes = [header, impl]
    if reverse:
        nodes.reverse()
    _merge_decl_def_classes(nodes, [])
    assert nodes == [header]
    assert (header["source_end_location"], header["definition_end_location"]) == ("L3", "L20")
    _merge_decl_def_classes(nodes, [])
    assert (header["source_end_location"], header["definition_end_location"]) == ("L3", "L20")
    unknown_end = {k: v for k, v in impl.items() if k != "source_end_location"}
    nodes.append(unknown_end)
    _merge_decl_def_classes(nodes, [])
    assert "definition_end_location" not in header
    assert header["source_end_location"] == "L3"


def test_query_and_get_node_print_the_declaration_range(tmp_path):
    from graphify import serve

    src = tmp_path / "svc.py"
    src.write_text("def run():\n    a = 1\n    return a\n\n\ndef one(): return 1\n")
    G = build([extract([src], tmp_path / "cache", root=tmp_path)])
    run = next(n for n, d in G.nodes(data=True) if d.get("label") == "run()")
    one = next(n for n, d in G.nodes(data=True) if d.get("label") == "one()")

    text = serve._subgraph_to_text(G, {run, one}, [])
    assert "loc=L1-L3 " in text
    # A one-line declaration keeps the start-only form.
    assert "loc=L6 " in text
    assert serve._node_location({"source_location": "L4", "source_end_location": 9}) == "L4"
    assert serve._node_location({"source_location": "L4", "source_end_location": "L2"}) == "L4"


def test_objc_interface_and_implementation_in_one_file_keep_one_contains_edge(tmp_path):
    path = tmp_path / "Box.m"
    path.write_text("@interface Box : NSObject\n- (void)run;\n@end\n@implementation Box\n- (void)run {}\n@end\n")
    result = _extract_file(path)
    box = _node(result, "Box")
    contains = [e for e in result["edges"] if e["relation"] == "contains" and e["target"] == box["id"]]
    assert len(contains) == 1
    assert box["definition_location"] == "L4"


def test_declarations_sharing_one_line_each_end_on_it(tmp_path):
    path = tmp_path / "bundle.min.js"
    path.write_text("function a(){return 1}function b(){return 2}const c=()=>3;\n")
    result = _extract_file(path)
    for label in ("a()", "b()", "c()"):
        node = _node(result, label)
        assert (node["source_location"], node["source_end_location"]) == ("L1", "L1")


@pytest.mark.parametrize("name, source, ranges", [
    ("A.java",
     "interface Greeter {\n    void greet(\n        String name);\n    int count();\n}\n"
     "abstract class Base {\n    abstract void run(\n        int x);\n}\n",
     {".greet()": ("L2", "L3"), ".count()": ("L4", "L4"), ".run()": ("L7", "L8")}),
    ("A.cs",
     "interface IGreeter {\n    void Greet(\n        string name);\n}\n"
     "abstract class Base {\n    public abstract void Run(\n        int x);\n}\n",
     {".Greet()": ("L2", "L3"), ".Run()": ("L6", "L7")}),
])
def test_bodiless_declarations_end_at_their_signature(tmp_path, name, source, ranges):
    path = tmp_path / name
    path.write_text(source)
    result = _extract_file(path)
    for label, expected in ranges.items():
        node = _node(result, label)
        assert (node["source_location"], node["source_end_location"]) == expected
