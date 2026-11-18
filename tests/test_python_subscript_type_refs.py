"""A Python subscript annotation does not count its own value as a generic arg.

``def f(x: mod.MyBox[Foo])`` parses the annotation as a ``subscript`` whose
value is ``mod.MyBox``. The collector walked the value, then skipped it among
the children with ``c is value``. py-tree-sitter returns a new ``Node`` object
on every access, so ``is`` never matched and ``MyBox`` was collected a second
time as a generic argument: a false ``references`` edge with
``context: generic_arg`` next to the real ``parameter_type`` one.
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter_python as tsp
from tree_sitter import Language, Parser

from graphify.extract import extract_python
from graphify.extractors.engine import _python_collect_type_refs


def _refs(annotation: str) -> list[tuple[str, str]]:
    src = f"def f(x: {annotation}): ...\n".encode()
    tree = Parser(Language(tsp.language())).parse(src)
    params = tree.root_node.children[0].child_by_field_name("parameters")
    assert params is not None
    typed = next(c for c in params.children if c.type == "typed_parameter")
    out: list[tuple[str, str]] = []
    _python_collect_type_refs(typed.child_by_field_name("type"), src, False, out)
    return out


def test_dotted_subscript_value_is_collected_once():
    assert _refs("mod.MyBox[Foo]") == [("MyBox", "type"), ("Foo", "generic_arg")]


def test_nested_dotted_subscript_value_is_collected_once():
    assert _refs("pkg.Wrap[mod.MyBox[Foo], Bar]") == [
        ("Wrap", "type"),
        ("MyBox", "generic_arg"),
        ("Foo", "generic_arg"),
        ("Bar", "generic_arg"),
    ]


def test_no_generic_arg_edge_to_the_subscripted_type(tmp_path: Path):
    path = tmp_path / "m.py"
    path.write_text(
        "import m as mod\n\n\n"
        "class MyBox:\n    pass\n\n\n"
        "class Foo:\n    pass\n\n\n"
        "def f(x: mod.MyBox[Foo]) -> mod.MyBox[Foo]:\n    return x\n"
    )
    result = extract_python(path)
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    refs = sorted(
        (labels.get(e["target"]), e.get("context"))
        for e in result["edges"]
        if e["relation"] == "references" and labels.get(e["source"]) == "f()"
    )
    assert refs == [
        ("Foo", "generic_arg"),
        ("MyBox", "parameter_type"),
        ("MyBox", "return_type"),
    ]
