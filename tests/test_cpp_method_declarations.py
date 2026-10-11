"""A C++ member-function DECLARATION is a method, not a data member.

Inside a class body a `virtual double area() = 0;` (pure virtual), a
`virtual void draw();` and a plain prototype `int run();` all parse as a
`field_declaration` whose declarator is a `function_declarator`. The field
branch emitted a node for every declarator as a data member (a bare `area`
label with a `defines`/field edge), so:

  * a pure-virtual interface class had NO method nodes, only phantom fields;
  * an out-of-line or overriding definition did not share the declaration's
    node, because one was `.area()` (method) and the other `area` (field);
  * a call to the method had nothing of the right shape to resolve to.

The fix emits a function_declarator with the same shape as a defined method
(`.name()` label, `method` edge, callable), while a genuine data member still
gets its `defines` field edge.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]) -> dict:
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        return extract([Path(n) for n in files], cache_root=Path(tempfile.mkdtemp()))
    finally:
        os.chdir(old)


def _rel(r: dict, relation: str, src: str, tgt: str) -> bool:
    labels = {n["id"]: str(n.get("label", "")) for n in r["nodes"]}
    return any(
        e.get("relation") == relation
        and labels.get(e.get("source")) == src
        and labels.get(e.get("target")) == tgt
        for e in r["edges"]
    )


def _labels(r: dict) -> list[str]:
    return [str(n.get("label", "")) for n in r["nodes"]]


def test_pure_virtual_method_is_a_method_node(tmp_path):
    r = _extract(tmp_path, {"s.cpp": (
        "class Shape {\n"
        "public:\n"
        "  virtual double area() = 0;\n"
        "};\n"
    )})
    assert _rel(r, "method", "Shape", ".area()")
    # Not misclassified as a data member.
    assert not _rel(r, "defines", "Shape", "area")
    assert "area" not in _labels(r)


def test_declared_virtual_and_prototype_are_methods(tmp_path):
    r = _extract(tmp_path, {"s.cpp": (
        "class Svc {\n"
        "public:\n"
        "  virtual void draw();\n"
        "  int run();\n"
        "};\n"
    )})
    assert _rel(r, "method", "Svc", ".draw()")
    assert _rel(r, "method", "Svc", ".run()")


def test_data_member_is_still_a_field(tmp_path):
    r = _extract(tmp_path, {"s.cpp": (
        "class Box {\n"
        "public:\n"
        "  int count;\n"
        "  double area() = 0;\n"
        "};\n"
    )})
    assert _rel(r, "defines", "Box", "count")
    assert _rel(r, "method", "Box", ".area()")


def test_override_definition_shares_the_declaration_node(tmp_path):
    # The abstract declaration and the concrete override are both `.area()`,
    # so a call through the base resolves instead of hitting a phantom field.
    r = _extract(tmp_path, {"s.cpp": (
        "class Shape {\n"
        "public:\n"
        "  virtual double area() = 0;\n"
        "  double describe() { return area(); }\n"
        "};\n"
    )})
    assert _rel(r, "method", "Shape", ".area()")
    assert _rel(r, "calls", ".describe()", ".area()")
