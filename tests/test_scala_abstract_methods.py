"""A deferred (abstract) Scala `def` is a method node, like a concrete one.

A bodyless `def area: Double` parses as `function_declaration`; a `def` WITH a
body is `function_definition`. Only the latter was a Scala function type, so
every abstract member was dropped. In Scala that is the common case, not an edge
case: a `trait` used as an interface is *all* deferred defs, so the whole
contract vanished from the graph — the trait had no method nodes, and a concrete
method calling a deferred one (`describe` → `name()`) had no target to link to.

These specs pin that the deferred method becomes a node in both a `trait` and an
`abstract class`, and that a call to it now resolves.
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


def test_deferred_method_without_parens_is_a_node(tmp_path):
    r = _extract(tmp_path, {"s.scala": (
        "trait Shape {\n"
        "  def area: Double\n"
        "}\n"
    )})
    assert _method_edge(r, "Shape", ".area()")


def test_deferred_method_with_params_is_a_node(tmp_path):
    r = _extract(tmp_path, {"s.scala": (
        "trait Shape {\n"
        "  def scale(f: Double): Shape\n"
        "}\n"
    )})
    assert _method_edge(r, "Shape", ".scale()")


def test_pure_interface_trait_keeps_every_contract_method(tmp_path):
    r = _extract(tmp_path, {"s.scala": (
        "trait Shape {\n"
        "  def area: Double\n"
        "  def name(): String\n"
        "  def describe: String = name()\n"
        "}\n"
    )})
    assert _method_edge(r, "Shape", ".area()")
    assert _method_edge(r, "Shape", ".name()")
    assert _method_edge(r, "Shape", ".describe()")
    # The concrete method's call now has a target to resolve to.
    assert _calls(r, ".describe()", ".name()")


def test_abstract_class_deferred_method_is_a_node(tmp_path):
    r = _extract(tmp_path, {"s.scala": (
        "abstract class Base {\n"
        "  def compute(x: Int): Int\n"
        "  def run(): Int = compute(1)\n"
        "}\n"
    )})
    assert _method_edge(r, "Base", ".compute()")
    assert _calls(r, ".run()", ".compute()")
