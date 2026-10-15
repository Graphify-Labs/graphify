"""An `abstract` method of an abstract class is a node, like an interface method.

`method_signature` (an interface's method) has been a TypeScript function type
for a while, so `interface Drawable { draw(): void }` puts `draw` in the graph.
An abstract class's `abstract area(): number;` parses as a DIFFERENT node,
`abstract_method_signature`, which was not a function type — so the abstract
method was dropped. The base of an `abstract class` kept only its concrete
methods, and a polymorphic `shape.area()` had no declaration to resolve to and
no node to carry the overridden contract.

An abstract method is the same kind of contract as an interface method: a
subclass must implement it. These specs pin that the declaration becomes a node
and that calls through it resolve, matching the interface behaviour.
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


def _method_edge(r: dict, owner: str, method: str) -> bool:
    labels = {n["id"]: str(n.get("label", "")) for n in r["nodes"]}
    return any(
        e.get("relation") == "method"
        and labels.get(e.get("source")) == owner
        and labels.get(e.get("target")) == method
        for e in r["edges"]
    )


def _calls(r: dict, src: str, tgt: str) -> bool:
    labels = {n["id"]: str(n.get("label", "")) for n in r["nodes"]}
    return any(
        e.get("relation") == "calls"
        and labels.get(e.get("source")) == src
        and labels.get(e.get("target")) == tgt
        for e in r["edges"]
    )


def test_abstract_method_becomes_a_node(tmp_path):
    r = _extract(tmp_path, {"s.ts": (
        "abstract class Shape {\n"
        "  abstract area(): number;\n"
        "}\n"
    )})
    assert _method_edge(r, "Shape", ".area()")


def test_abstract_and_concrete_methods_both_present(tmp_path):
    r = _extract(tmp_path, {"s.ts": (
        "abstract class Shape {\n"
        "  abstract area(): number;\n"
        "  describe(): string { return this.area().toString(); }\n"
        "}\n"
    )})
    assert _method_edge(r, "Shape", ".area()")
    assert _method_edge(r, "Shape", ".describe()")
    # The concrete method that calls the abstract one links to it.
    assert _calls(r, ".describe()", ".area()")


def test_call_through_abstract_type_resolves_to_the_declaration(tmp_path):
    r = _extract(tmp_path, {"s.ts": (
        "abstract class Shape {\n"
        "  abstract area(): number;\n"
        "}\n"
        "function use(s: Shape): number {\n"
        "  return s.area();\n"
        "}\n"
    )})
    assert _calls(r, "use()", ".area()")


def test_abstract_method_parity_with_interface_method(tmp_path):
    # Same shape via an interface already worked; the abstract class must match.
    r = _extract(tmp_path, {"s.ts": (
        "interface Drawable {\n"
        "  draw(): void;\n"
        "}\n"
        "abstract class Widget {\n"
        "  abstract draw(): void;\n"
        "}\n"
    )})
    assert _method_edge(r, "Drawable", ".draw()")
    assert _method_edge(r, "Widget", ".draw()")
