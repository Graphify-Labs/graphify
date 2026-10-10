"""Scala `type_definition` right-hand sides are never scanned for type references.

A type alias (`type Alias = List[Int]`), an `opaque type`, and a `match type`
all declare a dependency on the types they name, but the extractor's
type-reference dispatch only fired for `val_definition`/`var_definition`, so
these produced zero `references` edges of any kind in any context -- in
contrast to a `val`/`var`, whose annotation *is* walked. The `match_type` case
has a second, independent gap: the type-reference walker's own recursion
whitelist does not know `match_type`/`type_case_clause`, so even a correctly
dispatched call on a match type's right-hand side resolves nothing (#2049).

Scope note: the alias node itself (`type Alias = ...`) still gets no node of its
own. That is a separate, already-accepted tradeoff shared with `val`/`given`
bindings and is deliberately untouched here -- this change is only about the
edges the alias's right-hand side implies.

These tests pin every form (plain alias, `opaque type`, `match type`, a
multi-argument generic, and the file-scope position), that each bound type
resolves, that the matched type in a `match type` case is walked too, and that
the `val`/`var` context split is preserved rather than flattened.
"""
from pathlib import Path

from graphify.extract import extract_scala

SRC = '''\
class Marker
class Payload

trait Repo:
  type Alias = List[Payload]
  opaque type Id = Long
  type Elem[X] = X match
    case String => Char

type TopLevel = Map[String, Int]
opaque type OpaqueTop = Marker

class Holder {
  val plain: Payload = null
}
'''


def _build(tmp_path):
    (tmp_path / "Aliases.scala").write_text(SRC)
    r = extract_scala(tmp_path / "Aliases.scala")
    nid = {n["label"]: n["id"] for n in r["nodes"]}
    return r, nid


def _refs_from(r, src_label, nid):
    return {(e["target"], e.get("context")) for e in r["edges"]
            if e["relation"] == "references" and e["source"] == nid[src_label]}


def test_trait_type_alias_emits_reference_to_base_type(tmp_path):
    r, nid = _build(tmp_path)
    refs = _refs_from(r, "Repo", nid)
    assert (nid["List"], "field") in refs


def test_trait_type_alias_emits_reference_to_type_argument(tmp_path):
    r, nid = _build(tmp_path)
    refs = _refs_from(r, "Repo", nid)
    assert (nid["Payload"], "generic_arg") in refs


def test_opaque_type_emits_reference_to_underlying_type(tmp_path):
    r, nid = _build(tmp_path)
    refs = _refs_from(r, "Repo", nid)
    assert (nid["Long"], "field") in refs


def test_match_type_emits_reference_to_case_result(tmp_path):
    # `match_type` was the case that needed a walker change as well as a
    # dispatch change: without `match_type`/`type_case_clause` in the recursion
    # whitelist the dispatch would fire and still resolve nothing.
    r, nid = _build(tmp_path)
    refs = _refs_from(r, "Repo", nid)
    assert (nid["Char"], "field") in refs


def test_match_type_emits_reference_to_matched_type(tmp_path):
    # `case String =>` names a real type the alias discriminates on. The walk is
    # a plain recursion over named children, exactly as `compound_type` already
    # does, so the matched type is collected alongside the result.
    r, nid = _build(tmp_path)
    refs = _refs_from(r, "Repo", nid)
    assert any(t == nid["String"] for t, _c in refs)


def test_file_scope_type_alias_is_owned_by_the_file_node(tmp_path):
    # File-scope aliases need the same anchor fallback as file-scope `val`
    # (#2054); without it this edge is dropped by the same missing-container
    # defect.
    r, nid = _build(tmp_path)
    refs = _refs_from(r, "Aliases.scala", nid)
    assert (nid["Map"], "field") in refs
    assert (nid["String"], "generic_arg") in refs
    assert (nid["Int"], "generic_arg") in refs


def test_file_scope_opaque_type_is_owned_by_the_file_node(tmp_path):
    r, nid = _build(tmp_path)
    refs = _refs_from(r, "Aliases.scala", nid)
    assert (nid["Marker"], "field") in refs


def test_val_annotation_context_is_unchanged(tmp_path):
    # The `val`/`var` path and the `type_definition` path share this dispatch, so
    # pin that widening the tuple did not change the existing context split.
    r, nid = _build(tmp_path)
    refs = _refs_from(r, "Holder", nid)
    assert refs == {(nid["Payload"], "field")}


def test_type_definition_edges_are_tagged_extracted(tmp_path):
    r, nid = _build(tmp_path)
    edges = [e for e in r["edges"]
             if e["relation"] == "references"
             and e["source"] in (nid["Repo"], nid["Aliases.scala"])]
    assert edges
    for e in edges:
        assert e.get("confidence") == "EXTRACTED", e
        loc = e.get("source_location")
        assert isinstance(loc, str) and loc.startswith("L"), e


def test_alias_reference_never_points_at_the_owning_container(tmp_path):
    # The self-reference guard follows the anchor, so an alias whose right-hand
    # side names the enclosing type's own stem must not mint Repo -> Repo.
    r, nid = _build(tmp_path)
    for owner in ("Repo", "Aliases.scala"):
        assert not any(t == nid[owner] for t, _c in _refs_from(r, owner, nid))
