"""Scala 3 `extension` methods are members of the receiver type, not file scope (#2044).

`extension (p: Point) def flip` adds `flip` to `Point`, but tree-sitter-scala has
no name on `extension_definition` (the receiver sits inside its `parameters`), so
the walk fell through to the default recursion and every extension method became
a file-level function with no edge to the type it extends. The receiver's type
now owns them, the same way a Swift `extension Point` reuses `Point`'s node.
"""
from __future__ import annotations

from graphify.extract import extract, extract_scala

SRC = (
    "class Point(val x: Int):\n"
    "  def norm: Int = x\n"
    "\n"
    "extension (p: Point)\n"
    "  def flip(): Point = p\n"
    "  def twice: Int = flip().norm * 2\n"
    "\n"
    "extension (x: Int)\n"
    "  def double: Int = x * 2\n"
    "\n"
    "extension [A](xs: List[A])\n"
    "  def second: A = xs(1)\n"
    "\n"
    "extension (using ctx: Ctx)(s: String)\n"
    "  def shout: String = s\n"
    "\n"
    "extension (t: pkg.Thing) {\n"
    "  def first: Int = 1\n"
    "  def last: Int = 2\n"
    "}\n"
    "\n"
    "extension [T](t: T)\n"
    "  def self2: T = t\n"
)


def _graph(tmp_path):
    f = tmp_path / "ext.scala"
    f.write_text(SRC, encoding="utf-8")
    r = extract_scala(f)
    label = {n["id"]: str(n.get("label", "")) for n in r["nodes"]}
    return r, label


def _method(r, label, owner, method):
    return any(
        e.get("relation") == "method"
        and label.get(e.get("source")) == owner
        and label.get(e.get("target")) == method
        for e in r["edges"]
    )


def _file_contains(r, label, member):
    file_nid = next(n["id"] for n in r["nodes"] if n.get("label") == "ext.scala")
    return any(
        e.get("relation") == "contains" and e.get("source") == file_nid
        and label.get(e.get("target")) == member
        for e in r["edges"]
    )


def test_extension_on_local_class_attaches_to_that_class(tmp_path):
    r, label = _graph(tmp_path)
    assert _method(r, label, "Point", ".flip()")
    assert _method(r, label, "Point", ".twice()")
    assert not _file_contains(r, label, "flip()"), "extension method leaked to file scope"
    points = [n for n in r["nodes"] if n.get("label") == "Point"]
    assert len(points) == 1, f"extension must reuse the class node, got {points}"
    assert _method(r, label, "Point", ".norm()"), "class lost its own method"


def test_extension_on_external_and_generic_types(tmp_path):
    r, label = _graph(tmp_path)
    assert _method(r, label, "Int", ".double()")
    # a generic receiver binds to its head type, not the type argument
    assert _method(r, label, "List", ".second()")


def test_using_clause_is_not_the_receiver(tmp_path):
    r, label = _graph(tmp_path)
    assert _method(r, label, "String", ".shout()")
    assert not any(n.get("label") == "Ctx" and _method(r, label, "Ctx", ".shout()") for n in r["nodes"])


def test_qualified_receiver_and_braced_body(tmp_path):
    r, label = _graph(tmp_path)
    assert _method(r, label, "Thing", ".first()")
    assert _method(r, label, "Thing", ".last()")


def test_type_parameter_receiver_is_not_invented_as_a_type(tmp_path):
    r, label = _graph(tmp_path)
    # `extension [T](t: T)` extends every type; there is no `T` declaration to
    # own the method, so it stays at file scope rather than on a fabricated node.
    assert not any(n.get("label") == "T" for n in r["nodes"])
    assert _file_contains(r, label, "self2()")


def test_call_between_extension_methods_resolves(tmp_path):
    r, label = _graph(tmp_path)
    calls = {
        (label.get(e["source"]), label.get(e["target"]))
        for e in r["edges"] if e.get("relation") == "calls"
    }
    assert (".twice()", ".flip()") in calls


def test_extension_is_deterministic(tmp_path):
    a, _ = _graph(tmp_path)
    b, _ = _graph(tmp_path)
    key = lambda r: (sorted(n["id"] for n in r["nodes"]),
                     sorted((e["source"], e["relation"], e["target"]) for e in r["edges"]))
    assert key(a) == key(b)


def test_extension_in_another_file_attaches_to_the_real_class(tmp_path):
    # A sourced per-file `Point` copy would be a phantom duplicate of the real
    # class (#1402); the receiver must be the sourceless stub the corpus rewire
    # collapses onto `geo/Point.scala`'s node.
    (tmp_path / "geo").mkdir()
    point = tmp_path / "geo" / "Point.scala"
    point.write_text("class Point(val x: Int):\n  def norm: Int = x\n", encoding="utf-8")
    ops = tmp_path / "geo" / "PointOps.scala"
    ops.write_text("extension (p: Point)\n  def flip(): Point = p\n", encoding="utf-8")
    fwd = tmp_path / "Fwd.scala"
    fwd.write_text("extension (v: Vec)\n  def len(): Int = 1\n\nclass Vec:\n  def dim: Int = 2\n",
                   encoding="utf-8")
    r = extract([point, ops, fwd], cache_root=tmp_path, parallel=False)
    by_id = {n["id"]: n for n in r["nodes"]}
    owners = {
        by_id[e["target"]]["label"]: by_id[e["source"]]
        for e in r["edges"] if e.get("relation") == "method"
    }
    assert owners[".flip()"]["source_file"].endswith("Point.scala")
    assert owners[".flip()"]["id"] == owners[".norm()"]["id"]
    assert owners[".len()"]["id"] == owners[".dim()"]["id"], "forward-declared receiver split in two"
    assert sum(1 for n in r["nodes"] if n.get("label") == "Point") == 1
