"""Nested Python class definitions must keep their lexical owner (#4220)."""

from graphify.extract import extract


SOURCE = (
    "class Forward:\n"
    "    class Params:\n"
    "        def value(self): return 1\n"
    "    class Wrapper:\n"
    "        class Params:\n"
    "            def value(self): return 2\n"
    "class Backward:\n"
    "    class Params:\n"
    "        def value(self): return 3\n"
)


def _extract(root, source=SOURCE):
    root.mkdir(parents=True, exist_ok=True)
    path = root / "scheduler.py"
    path.write_text(source, encoding="utf-8")
    return extract([path], root=root, cache_root=root / "cache", parallel=False)


def test_same_named_nested_classes_keep_nodes_methods_and_parent(tmp_path):
    result = _extract(tmp_path)
    params = [node for node in result["nodes"] if node["label"] == "Params"]
    assert len(params) == 3
    assert len({node["id"] for node in params}) == 3
    assert {node["source_location"] for node in params} == {"L2", "L5", "L8"}
    owners = {node["id"]: node["label"] for node in result["nodes"]}
    expected = {"L2": "Forward", "L5": "Wrapper", "L8": "Backward"}
    for node in params:
        parents = [edge["source"] for edge in result["edges"]
                   if edge["relation"] == "contains" and edge["target"] == node["id"]]
        assert len(parents) == 1
        assert owners[parents[0]] == expected[node["source_location"]]
        methods = [edge["target"] for edge in result["edges"]
                   if edge["relation"] == "method" and edge["source"] == node["id"]]
        assert len(methods) == 1
        assert owners[methods[0]] == ".value()"
    assert len([node for node in result["nodes"] if node["label"] == ".value()"]) == 3


def test_same_name_as_parent_has_distinct_identity(tmp_path):
    result = _extract(tmp_path, "class Params:\n    class Params:\n        pass\n")
    params = [node for node in result["nodes"] if node["label"] == "Params"]
    assert len(params) == 2
    outer, inner = sorted(params, key=lambda node: node["source_location"])
    assert outer["id"] == "scheduler_params"
    assert outer["id"] != inner["id"]
    assert any(edge["source"] == outer["id"] and edge["target"] == inner["id"]
               and edge["relation"] == "contains" for edge in result["edges"])


def test_nested_class_identity_is_stable_across_cache_and_checkout(tmp_path):
    first = _extract(tmp_path / "first")
    warm = _extract(tmp_path / "first")
    relocated = _extract(tmp_path / "second")
    assert first["nodes"] == warm["nodes"] == relocated["nodes"]
    assert first["edges"] == warm["edges"] == relocated["edges"]


def test_nested_class_decorators_and_docstrings_have_real_owners(tmp_path):
    result = _extract(tmp_path, (
        "def decorate(cls): return cls\n"
        "class Outer:\n"
        "    @decorate\n"
        "    class Inner:\n"
        "        \"\"\"This class holds the nested parameters for the outer class.\"\"\"\n"
        "        def value(self):\n"
        "            \"\"\"Return the value owned by this nested class instance.\"\"\"\n"
        "            return 1\n"
    ))
    nodes = {node["id"]: node for node in result["nodes"]}
    inner = next(node["id"] for node in nodes.values() if node["label"] == "Inner")
    method = next(node["id"] for node in nodes.values() if node["label"] == ".value()")
    assert any(edge["source"] == inner and edge.get("context") == "decorator"
               for edge in result["edges"])
    rationales = [edge for edge in result["edges"] if edge["relation"] == "rationale_for"]
    assert {edge["target"] for edge in rationales} == {inner, method}
    assert all(edge["source"] in nodes and edge["target"] in nodes for edge in rationales)
