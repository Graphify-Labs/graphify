"""Scala top-level (file-scope) `val`/`var` bindings lose every type reference.

Scala 3's headline feature is dropping the boilerplate wrapper: `val`, `var`,
`given` and `def` can be written directly at file scope with no enclosing
`object`/`class`/`trait`. The `val_definition`/`var_definition` type-reference
dispatch was gated on `and parent_class_nid`, so a file-scope binding silently
produced no node and no edge of any kind -- the exact same definition nested one
level inside any container resolved correctly. The gate was the only difference:
both positions parse to an identical `val_definition` with a `type` field.

The same generic mechanism in the walker's default recursion path had already
caused and been fixed once for a Python-specific case (#1050), so this is the
Scala instance of a known defect rather than a new one.

These tests pin the anchor fallback: a file-scope binding attributes its type
reference to the file node, a class-nested binding is unchanged, and the
self-reference guard follows the anchor so a file-scope binding whose type
resolves to the file's own stem does not mint an edge to itself.
"""
from pathlib import Path

from graphify.extract import extract_scala

SRC = '''\
class Inner {
  val nested: String = "x"
  var nestedCounter: Int = 0
}

val greeting: String = "World"
var counter: Int = 0

trait Config
val config: Config = null

val names: List[String] = Nil
'''


def _build(tmp_path):
    (tmp_path / "TopLevel.scala").write_text(SRC)
    r = extract_scala(tmp_path / "TopLevel.scala")
    nid = {n["label"]: n["id"] for n in r["nodes"]}
    return r, nid


def _rels(r, relation):
    return {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "references"}


def test_class_nested_binding_keeps_its_type_reference(tmp_path):
    # Control: the pre-existing in-class behaviour must not regress. The edge is
    # owned by the class, not the file.
    r, nid = _build(tmp_path)
    refs = _rels(r, "references")
    assert (nid["Inner"], nid["String"]) in refs


def test_top_level_val_emits_type_reference_owned_by_file(tmp_path):
    r, nid = _build(tmp_path)
    refs = _rels(r, "references")
    file_nid = nid["TopLevel.scala"]
    assert (file_nid, nid["String"]) in refs


def test_top_level_var_emits_type_reference_owned_by_file(tmp_path):
    r, nid = _build(tmp_path)
    refs = _rels(r, "references")
    file_nid = nid["TopLevel.scala"]
    assert (file_nid, nid["Int"]) in refs


def test_top_level_binding_type_resolves_to_another_declaration(tmp_path):
    # The type is a real declaration elsewhere in the corpus, so the reference
    # must land on that node rather than on a bare stub.
    r, nid = _build(tmp_path)
    refs = _rels(r, "references")
    file_nid = nid["TopLevel.scala"]
    assert (file_nid, nid["Config"]) in refs


def test_top_level_binding_emits_no_self_edge(tmp_path):
    # The self-reference guard compared against parent_class_nid, which is None at
    # file scope. Anchoring on the file node must keep the guard working there,
    # otherwise a binding typed with the file's own stem mints file -> file.
    r, nid = _build(tmp_path)
    file_nid = nid["TopLevel.scala"]
    refs = _rels(r, "references")
    assert not any(src == file_nid and tgt == file_nid for src, tgt in refs)


def test_top_level_type_reference_is_tagged_extracted(tmp_path):
    # A type annotation written in the source is an extracted fact, not an
    # inference: the confidence tag must say so, or a consumer cannot tell a
    # real annotation from a guess (#2054).
    r, nid = _build(tmp_path)
    file_nid = nid["TopLevel.scala"]
    edges = [e for e in r["edges"]
             if e["relation"] == "references" and e["source"] == file_nid]
    assert edges, "expected the file node to own the top-level type references"
    for e in edges:
        assert e.get("confidence") == "EXTRACTED", e


def test_top_level_type_reference_carries_source_location(tmp_path):
    # The edge must point at the line the annotation is written on, so a query
    # can cite it without a second file read. Locations serialise as "L<line>".
    r, nid = _build(tmp_path)
    file_nid = nid["TopLevel.scala"]
    edges = [e for e in r["edges"]
             if e["relation"] == "references" and e["source"] == file_nid]
    assert edges
    locs = set()
    for e in edges:
        loc = e.get("source_location")
        assert isinstance(loc, str) and loc.startswith("L"), e
        locs.add(int(loc[1:]))
    # `val greeting` L6, `var counter` L7, `val config` L10, `val names` L12 --
    # all strictly inside the file, never the default line 1.
    assert locs == {6, 7, 10, 12}, locs


def test_top_level_generic_annotation_keeps_its_own_context(tmp_path):
    # `List[String]` at file scope must resolve BOTH the base type and the type
    # argument, and the argument keeps its own `generic_arg` context rather than
    # being flattened into the plain `field` shape -- so a consumer can tell a
    # type argument from a plain annotation. The type parameter `String` is
    # shadowed by the real `String` node, which is exactly the resolution the
    # in-class path already performs.
    r, nid = _build(tmp_path)
    refs = _rels(r, "references")
    file_nid = nid["TopLevel.scala"]
    assert (file_nid, nid["List"]) in refs
    assert (file_nid, nid["String"]) in refs
    ctxs = {(tgt, e.get("context")) for e in r["edges"]
            if e["relation"] == "references" and e["source"] == file_nid
            for tgt in (e["target"],)}
    assert (nid["List"], "field") in ctxs
    assert (nid["String"], "generic_arg") in ctxs
