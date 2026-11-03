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
    assert node.get("metadata", {}).get("end_line") == end, node
    for other in result["nodes"]:
        if other["label"] == path.name or not other.get("source_file"):
            assert "end_line" not in other.get("metadata", {}), other


@pytest.mark.parametrize("end_point, expected", [((4, 0), 4), ((4, 3), 5), ((0, 5), 1)])
def test_exclusive_end_point(end_point, expected):
    from graphify.extractors.base import _inclusive_end_line

    ast_node = SimpleNamespace(start_point=(0, 0), end_point=end_point)
    assert _inclusive_end_line(ast_node) == expected


def test_go_receiver_owner_has_no_range_and_real_type_wins(tmp_path):
    path = tmp_path / "sample.go"
    path.write_text(
        "package p\nfunc (b Box) Run() {\n}\ntype Box struct {\n value int\n}\n",
        encoding="utf-8",
    )
    result = _extract_file(path)
    method = _node(result, ".Run()")
    assert method.get("metadata", {}).get("end_line") == 3
    owner = _node(result, "Box")
    assert owner["source_location"] == "L4"
    assert owner.get("metadata", {}).get("end_line") == 6
    path.write_text("package p\nfunc (b Foreign) Run() {}\n", encoding="utf-8")
    owner = _node(_extract_file(path), "Foreign")
    assert "end_line" not in owner.get("metadata", {})


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
        assert node.get("metadata", {}).get("end_line") == source_end
        assert node.get("metadata", {}).get("definition_end_line") == def_end
    before = copy.deepcopy(result)
    _merge_decl_def_classes(result["nodes"], result["edges"])
    assert result == before
    graph = build([result, copy.deepcopy(result)], root=tmp_path)
    prefixed = prefix_graph_for_global(graph, "example")
    for node in result["nodes"]:
        if node["label"] in {"Box", "-run"}:
            assert graph.nodes[node["id"]]["metadata"] == node["metadata"]
            assert prefixed.nodes[f"example::{node['id']}"]["metadata"] == node["metadata"]
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output))
    saved = json.loads(output.read_text())
    assert _node(saved, "-run")["metadata"]["definition_end_line"] == 6
    import graphify.global_graph as global_graph

    global_dir = tmp_path / "global"
    monkeypatch.setattr(global_graph, "_GLOBAL_DIR", global_dir)
    monkeypatch.setattr(global_graph, "_GLOBAL_GRAPH", global_dir / "graph.json")
    monkeypatch.setattr(global_graph, "_GLOBAL_MANIFEST", global_dir / "manifest.json")
    global_graph.global_add(output, "example")
    stored = global_graph._load_global_graph()
    method_id = _node(result, "-run")["id"]
    assert stored.nodes[f"example::{method_id}"]["metadata"]["definition_end_line"] == 6


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
        assert node["metadata"]["end_line"] == source_end
        assert node["definition_file"] == "Box.m"
        assert node["definition_location"] == f"L{definition_start}"
        assert node["metadata"]["definition_end_line"] == definition_end
    before = copy.deepcopy(result)
    _merge_decl_def_classes(result["nodes"], result["edges"])
    assert result == before


@pytest.mark.parametrize("reverse", [False, True])
def test_duplicate_merge_fills_range_only_for_matching_location(reverse):
    from graphify.dedup import _merge_missing_attributes

    keeper = {"source_file": "sample.py", "source_location": "L2", "metadata": {"kind": "fn"}}
    same = {"source_file": "sample.py", "source_location": "L2", "metadata": {"end_line": 4}}
    first, second = (same, keeper) if reverse else (keeper, same)
    merged = _merge_missing_attributes(first, second)
    assert merged["metadata"]["end_line"] == 4
    assert first == (same if reverse else keeper)
    different = {**same, "source_location": "L8"}
    assert "end_line" not in _merge_missing_attributes(keeper, different)["metadata"]
    no_metadata = {k: v for k, v in keeper.items() if k != "metadata"}
    assert "end_line" not in _merge_missing_attributes(no_metadata, different)["metadata"]


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
        assert node["metadata"]["end_line"] == source_end
        assert node.get("definition_file") == str(path)
        assert node.get("definition_location") == f"L{definition_start}"
        assert node["metadata"].get("definition_end_line") == definition_end


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
    assert enum.get("metadata", {}).get("end_line") == 5
    assert _node(result, "Red").get("metadata", {}).get("end_line") == 2


def test_cached_extraction_retains_ranges(tmp_path):
    path = tmp_path / "sample.py"
    path.write_text("def run():\n    return 1\n", encoding="utf-8")
    first = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    second = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert _node(first, "run()")["metadata"]["end_line"] == 2
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
        "source_location": "L2", "file_type": "code", "metadata": {"end_line": 4},
    }
    duplicate = {**complete, "metadata": {"kind": "function", "arity": 0}}
    nodes = [complete, duplicate]
    if reverse:
        nodes.reverse()
    graph = build([{"nodes": nodes, "edges": []}])
    assert graph.nodes["run"]["metadata"]["end_line"] == 4
    assert complete["metadata"] == {"end_line": 4}


@pytest.mark.parametrize("header_has_definition", [False, True])
@pytest.mark.parametrize("known_end", [False, True])
def test_definition_merge_uses_explicit_implementation_site(header_has_definition, known_end):
    header = {
        "id": "box", "label": "Box", "file_type": "code", "source_file": "Box.h",
        "source_location": "L1", "metadata": {"end_line": 3},
    }
    if header_has_definition:
        header.update(definition_file="Box.m", definition_location="L8")
        header["metadata"]["definition_end_line"] = 12
    impl = {
        **header, "source_file": "Box.m", "source_location": "L2",
        "definition_file": "Box.m", "definition_location": "L5", "metadata": {"end_line": 4},
    }
    if known_end:
        impl["metadata"]["definition_end_line"] = 9
    nodes = [header, impl]
    _merge_decl_def_classes(nodes, [])
    assert nodes == [header]
    assert header["source_file"] == "Box.h"
    assert header["source_location"] == "L1"
    assert header["metadata"]["end_line"] == 3
    assert header["definition_file"] == "Box.m"
    assert header["definition_location"] == "L5"
    assert header["metadata"].get("definition_end_line") == (9 if known_end else None)
    before = copy.deepcopy(header)
    _merge_decl_def_classes(nodes, [])
    assert header == before


@pytest.mark.parametrize("reverse", [False, True])
def test_definition_merge_keeps_separate_ranges(reverse):
    header = {
        "id": "box", "label": "Box", "file_type": "code", "source_file": "Box.h",
        "source_location": "L1", "metadata": {"end_line": 3},
    }
    impl = {
        **header, "source_file": "Box.m", "source_location": "L10",
        "metadata": {"end_line": 20},
    }
    nodes = [header, impl]
    if reverse:
        nodes.reverse()
    _merge_decl_def_classes(nodes, [])
    assert nodes == [header]
    assert header["metadata"] == {"end_line": 3, "definition_end_line": 20}
    _merge_decl_def_classes(nodes, [])
    assert header["metadata"] == {"end_line": 3, "definition_end_line": 20}
    unknown_end = {**impl, "metadata": {}}
    nodes.append(unknown_end)
    _merge_decl_def_classes(nodes, [])
    assert "definition_end_line" not in header["metadata"]
    assert header["metadata"]["end_line"] == 3
