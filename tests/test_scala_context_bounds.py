"""Scala context bounds (`[A: Ordering]`) never produce a `references` edge.

Context bounds are the standard sugar for typeclass-parameter wiring in
idiomatic Scala, and are more common in modern code than the desugared
`(implicit ...)` form they compile to. The `context_bound` node type was not
referenced anywhere in the extractor, so a type parameter's constraint was
invisible no matter where in the file it appeared (#2046).

The grammar shapes this precisely, and two of them drive the fix:

- `context_bound` is a direct child of `type_parameters`, one per bound, sitting
  alongside the type parameter's own `identifier`.
- For a higher-kinded parameter the nested arity brackets are a *nested*
  `type_parameters` (`F[_]`), so the walk has to recurse rather than take direct
  children only, or `[F[_]: Async: Temporal]` yields nothing.

Two deliberate non-emissions are pinned as well. An `upper_bound` (`[T <: C]`)
is a separate node type and is a subtype constraint, not a dependency, so it
must not emit an edge. And `type_parameters` and `parameters` share the *same*
field name on `function_definition`, so the sibling walk must match on node type
-- looking the node up by field name would return the type parameters and read
the function's real parameters as if they were bounds.
"""
from pathlib import Path

from graphify.extract import extract_scala

SRC = '''\
trait Ordering
trait Async
trait Temporal
trait Comparable

def sort[A: Ordering](xs: List[A]): List[A] = xs

def program[F[_]: Async: Temporal](x: F[Int]): F[Int] = x

def plain[T](t: T): T = t

def bounded[T <: Comparable[T]](t: T): T = t

class Container {
  def member[K: Ordering](k: K): K = k
}
'''


def _build(tmp_path):
    (tmp_path / "ContextBounds.scala").write_text(SRC)
    r = extract_scala(tmp_path / "ContextBounds.scala")
    nid = {n["label"]: n["id"] for n in r["nodes"]}
    return r, nid


def _bound_targets(r, func_label, nid):
    """References from `func_label` whose context is `type_bound`."""
    return {e["target"] for e in r["edges"]
            if e["relation"] == "references"
            and e["source"] == nid[func_label]
            and e.get("context") == "type_bound"}


def test_single_context_bound_emits_reference(tmp_path):
    r, nid = _build(tmp_path)
    assert nid["Ordering"] in _bound_targets(r, "sort()", nid)


def test_several_context_bounds_each_emit_a_reference(tmp_path):
    r, nid = _build(tmp_path)
    targets = _bound_targets(r, "program()", nid)
    assert nid["Async"] in targets
    assert nid["Temporal"] in targets


def test_nested_type_parameters_do_not_hide_the_bounds(tmp_path):
    # `F[_]` nests a type_parameters inside type_parameters. A direct-children
    # walk would miss both bounds on `program` entirely.
    r, nid = _build(tmp_path)
    targets = _bound_targets(r, "program()", nid)
    assert len(targets) >= 2, targets


def test_context_bound_uses_its_own_context_not_parameter_type(tmp_path):
    # A typeclass constraint is not a parameter type. Reusing `parameter_type`
    # would make the two indistinguishable to a consumer.
    r, nid = _build(tmp_path)
    edges = [e for e in r["edges"]
             if e["relation"] == "references" and e["source"] == nid["sort()"]]
    bound = [e for e in edges if e.get("context") == "type_bound"]
    assert bound, "expected a type_bound context"
    assert all(e.get("context") != "parameter_type" for e in bound)


def test_unbounded_type_parameter_emits_no_bound_edge(tmp_path):
    r, nid = _build(tmp_path)
    assert not _bound_targets(r, "plain()", nid)


def test_upper_bound_emits_no_bound_edge(tmp_path):
    # `[T <: Comparable[T]]` is an `upper_bound`, a distinct node type. It states
    # a subtype constraint, not a dependency, so it must not become an edge.
    r, nid = _build(tmp_path)
    assert not _bound_targets(r, "bounded()", nid)


def test_context_bound_does_not_swallow_the_functions_own_parameters(tmp_path):
    # `type_parameters` and `parameters` share the field name "parameters" on
    # `function_definition`. A field-name lookup would pick the type parameters
    # and read `xs: List[A]` as a bound, so this pins that the real parameter
    # type still resolves under the `parameter_type` context.
    r, nid = _build(tmp_path)
    refs = {(e["target"], e.get("context")) for e in r["edges"]
            if e["relation"] == "references" and e["source"] == nid["sort()"]}
    assert (nid["List"], "parameter_type") in refs
    assert (nid["List"], "type_bound") not in refs


def test_member_function_bound_is_attributed_to_the_member(tmp_path):
    # Class members carry a dotted label (`.member()`); top-level defs do not.
    r, nid = _build(tmp_path)
    assert nid["Ordering"] in _bound_targets(r, ".member()", nid)


def test_bound_edge_is_tagged_extracted_with_a_location(tmp_path):
    r, nid = _build(tmp_path)
    edges = [e for e in r["edges"]
             if e["relation"] == "references"
             and e.get("context") == "type_bound"]
    assert edges
    for e in edges:
        assert e.get("confidence") == "EXTRACTED", e
        loc = e.get("source_location")
        assert isinstance(loc, str) and loc.startswith("L"), e


def test_bound_never_points_at_the_function_itself(tmp_path):
    r, nid = _build(tmp_path)
    for label in ("sort()", "program()", ".member()"):
        assert nid[label] not in _bound_targets(r, label, nid)


# Class-level context bounds (#4080). `class_definition`, `trait_definition`
# and `enum_definition` carry the same `type_parameters` node as a method, so
# the bound is the same typeclass dependency, attributed to the type itself.
CLASS_SRC = '''\
trait Ordering
trait Show
trait Eq
trait Async
trait Comparable

class Sorted[A: Ordering](xs: List[A])

case class Pretty[T: Show: Eq](t: T)

trait Effectful[F[_]: Async]

enum Ranked[A: Ordering] { case Low }

class Plain[T](t: T)

class Upper[T <: Comparable[T]](t: T)

class Holder {
  def member[K: Ordering](k: K): K = k
}
'''


def _build_classes(tmp_path):
    (tmp_path / "ClassContextBounds.scala").write_text(CLASS_SRC)
    r = extract_scala(tmp_path / "ClassContextBounds.scala")
    nid = {n["label"]: n["id"] for n in r["nodes"]}
    return r, nid


def test_class_context_bound_emits_reference(tmp_path):
    r, nid = _build_classes(tmp_path)
    assert nid["Ordering"] in _bound_targets(r, "Sorted", nid)


def test_case_class_several_context_bounds_each_emit_a_reference(tmp_path):
    r, nid = _build_classes(tmp_path)
    targets = _bound_targets(r, "Pretty", nid)
    assert nid["Show"] in targets
    assert nid["Eq"] in targets


def test_trait_higher_kinded_context_bound_emits_reference(tmp_path):
    r, nid = _build_classes(tmp_path)
    assert nid["Async"] in _bound_targets(r, "Effectful", nid)


def test_enum_context_bound_emits_reference(tmp_path):
    r, nid = _build_classes(tmp_path)
    assert nid["Ordering"] in _bound_targets(r, "Ranked", nid)


def test_class_without_context_bound_emits_no_bound_edge(tmp_path):
    r, nid = _build_classes(tmp_path)
    assert not _bound_targets(r, "Plain", nid)
    assert not _bound_targets(r, "Upper", nid)


def test_class_context_bound_keeps_constructor_param_as_field(tmp_path):
    # The bound must not displace the class_parameters walk: `xs: List[A]`
    # still references List under the `field` context.
    r, nid = _build_classes(tmp_path)
    refs = {(e["target"], e.get("context")) for e in r["edges"]
            if e["relation"] == "references" and e["source"] == nid["Sorted"]}
    assert (nid["List"], "field") in refs
    assert (nid["List"], "type_bound") not in refs


def test_member_bound_is_not_hoisted_to_the_enclosing_class(tmp_path):
    r, nid = _build_classes(tmp_path)
    assert nid["Ordering"] in _bound_targets(r, ".member()", nid)
    assert not _bound_targets(r, "Holder", nid)


def test_class_bound_edge_is_tagged_extracted_with_a_location(tmp_path):
    r, nid = _build_classes(tmp_path)
    edges = [e for e in r["edges"]
             if e["relation"] == "references"
             and e["source"] == nid["Sorted"]
             and e.get("context") == "type_bound"]
    assert edges
    for e in edges:
        assert e.get("confidence") == "EXTRACTED", e
        assert e.get("source_location") == "L7", e
