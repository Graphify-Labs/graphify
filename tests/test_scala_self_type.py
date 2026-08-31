"""Scala self-type annotations (`self: Logging with Database =>`, `this: T =>`).

A trait/class's self-type declares a structural precondition on the enclosing
type ("this can only be mixed into something also providing X") -- the
cake-pattern idiom. `self_type` was never dispatched on anywhere in the
extractor, so it produced no edges at all, in any context (#2052). These
tests pin the new dispatch branch: every real type shape a self-type can
carry, the negative case where no type is present, that an ordinary class
without a self-type never gains a spurious edge, that the new `requires`
relation coexists cleanly with an unrelated `extends` on the same class, and
that `affected` (blast radius) now traverses it.
"""
from pathlib import Path

import networkx as nx

from graphify.affected import affected_nodes
from graphify.extract import extract_scala

SRC = '''\
trait Loggable
trait Database
trait HasConfig
trait BaseTrait

class SimpleSelfType {
  self: HasConfig =>

  def configure(): Unit = ()
}

class CompoundSelfType {
  self: Loggable with Database =>

  def run(): Unit = ()
}

class RefinedSelfType {
  self: Loggable { def extra: Int } =>

  def refined(): Unit = ()
}

class BinderOnlySelfType {
  self =>

  def noop(): Unit = ()
}

class NoSelfType {
  def plain(): Unit = ()
}

class SelfTypeWithExtends extends BaseTrait {
  self: Loggable =>

  def combined(): Unit = ()
}
'''


def _build(tmp_path):
    (tmp_path / "SelfTypes.scala").write_text(SRC)
    r = extract_scala(tmp_path / "SelfTypes.scala")
    nid = {n["label"]: n["id"] for n in r["nodes"]}
    return r, nid


def _rels(r, relation):
    return {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == relation}


def test_self_type_simple_type_emits_requires(tmp_path):
    r, nid = _build(tmp_path)
    requires = _rels(r, "requires")
    assert (nid["SimpleSelfType"], nid["HasConfig"]) in requires


def test_self_type_compound_with_emits_requires_for_each_member(tmp_path):
    r, nid = _build(tmp_path)
    requires = _rels(r, "requires")
    assert (nid["CompoundSelfType"], nid["Loggable"]) in requires
    assert (nid["CompoundSelfType"], nid["Database"]) in requires


def test_self_type_structural_refinement_emits_requires_for_base_only(tmp_path):
    r, nid = _build(tmp_path)
    requires = _rels(r, "requires")
    assert (nid["RefinedSelfType"], nid["Loggable"]) in requires
    # The refinement body's own member signature (`def extra: Int`) is not
    # walked -- consistent with every other refinement-type context in this
    # extractor (a plain `val x: Loggable { def extra: Int }` behaves the
    # same way), not a new limitation introduced here.
    assert "extra" not in nid


def test_self_type_binder_only_emits_no_requires_edge(tmp_path):
    r, nid = _build(tmp_path)
    requires = _rels(r, "requires")
    binder_only = nid["BinderOnlySelfType"]
    assert not any(src == binder_only for src, _tgt in requires)


def test_class_without_self_type_emits_no_requires_edge(tmp_path):
    r, nid = _build(tmp_path)
    requires = _rels(r, "requires")
    no_self_type = nid["NoSelfType"]
    assert not any(src == no_self_type for src, _tgt in requires)


def test_self_type_coexists_with_unrelated_extends(tmp_path):
    r, nid = _build(tmp_path)
    inherits = _rels(r, "inherits")
    requires = _rels(r, "requires")
    combined = nid["SelfTypeWithExtends"]
    # extends_clause and self_type are independent code paths -- both fire
    # on the same class with no conflict.
    assert (combined, nid["BaseTrait"]) in inherits
    assert (combined, nid["Loggable"]) in requires


def test_requires_edges_carry_no_context(tmp_path):
    r, _nid = _build(tmp_path)
    for e in r["edges"]:
        if e["relation"] == "requires":
            assert "context" not in e


def test_affected_includes_self_type_dependents(tmp_path):
    r, nid = _build(tmp_path)
    g = nx.DiGraph()
    for n in r["nodes"]:
        g.add_node(n["id"], **n)
    for e in r["edges"]:
        g.add_edge(e["source"], e["target"], **e)

    # HasConfig's blast radius now includes SimpleSelfType through `requires`
    # (DEFAULT_AFFECTED_RELATIONS), mirroring how `inherits`/`mixes_in` are
    # already traversed.
    affected = {h.node_id for h in affected_nodes(g, nid["HasConfig"])}
    assert nid["SimpleSelfType"] in affected
