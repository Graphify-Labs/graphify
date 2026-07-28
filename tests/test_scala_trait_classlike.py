"""Regression tests: Scala `trait` recognized as a class-like container.

`trait_definition` is tree-sitter-scala's own node kind for `trait Foo { ... }`,
distinct from `class_definition`/`object_definition`. It was absent from
`_SCALA_CONFIG.class_types`, so `walk()`'s class-node branch never matched a
trait: no node represented the trait itself, its `extends_clause` heritage was
never evaluated (no `inherits`/`mixes_in` edges), and every member underneath
it fell to the generic "default: recurse" branch, which resets
`parent_class_nid` to `None` -- so a trait's own `val`/`def` surfaced (if at
all) as if it belonged to the file, not the trait. A trait uses the same
`template_body` shape already declared in `body_fallback_child_types`, so
recognizing it needs no new handler: the existing heritage/field-reference
code that already runs for `class_definition`/`object_definition` picks it up
unchanged.

Known limitation, not covered here: a same-named trait and companion object
(`trait Foo` + `object Foo`) now collide onto one node the same way a
same-named class and companion object already did on `class_types` alone,
before this file's change -- see the PR body. That pre-existing collision,
and any fix for it, is out of scope for this diff.
"""
from __future__ import annotations

from pathlib import Path

import networkx as nx

from graphify.affected import affected_nodes
from graphify.extract import _file_stem, _make_id, extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _node(result: dict, file: str, sym: str) -> dict | None:
    nid = _make_id(_file_stem(Path(file)), sym)
    return next((n for n in result["nodes"] if n["id"] == nid), None)


def _has_node(result: dict, file: str, sym: str) -> bool:
    return _node(result, file, sym) is not None


def _edges(result: dict, relation: str) -> list[dict]:
    return [e for e in result["edges"] if e["relation"] == relation]


def _label_of(result: dict, node_id: str) -> str:
    return next((n["label"] for n in result["nodes"] if n["id"] == node_id), node_id)


def _owners_of_relation(result: dict, relation: str, target_substr: str) -> set[str]:
    """Source-node labels of every `relation` edge whose target label contains
    `target_substr` -- used to check which node a member (method/field ref)
    ended up attached to."""
    return {
        _label_of(result, e["source"])
        for e in _edges(result, relation)
        if target_substr in _label_of(result, e["target"])
    }


def _to_digraph(result: dict) -> nx.DiGraph:
    g = nx.DiGraph()
    for n in result["nodes"]:
        g.add_node(n["id"], **n)
    for e in result["edges"]:
        g.add_edge(e["source"], e["target"], relation=e["relation"])
    return g


# ── Positive: a trait becomes its own class-like node ──────────────────────

def test_bare_trait_is_a_node(tmp_path):
    f = _write(tmp_path / "src" / "Marker.scala",
               "package demo\n\ntrait Marker\n")
    r = extract([f], cache_root=tmp_path)
    assert _has_node(r, "src/Marker.scala", "Marker")


def test_trait_heritage_splits_inherits_and_mixes_in_onto_real_nodes(tmp_path):
    f = _write(tmp_path / "src" / "Widget.scala",
               "package demo\n\n"
               "trait Drawable\n"
               "trait Loggable\n\n"
               "trait Widget extends Drawable with Loggable\n")
    r = extract([f], cache_root=tmp_path)
    inherits = {(_label_of(r, e["source"]), _label_of(r, e["target"])) for e in _edges(r, "inherits")}
    mixes_in = {(_label_of(r, e["source"]), _label_of(r, e["target"])) for e in _edges(r, "mixes_in")}
    assert ("Widget", "Drawable") in inherits
    assert ("Widget", "Loggable") in mixes_in
    # Before the fix these targets only existed as sourceless stubs
    # (`ensure_named_node`, source_file=""); recognizing trait_definition
    # gives them real nodes with a real source_file/source_location.
    drawable = _node(r, "src/Widget.scala", "Drawable")
    loggable = _node(r, "src/Widget.scala", "Loggable")
    assert drawable is not None and drawable["source_file"] == "src/Widget.scala"
    assert loggable is not None and loggable["source_file"] == "src/Widget.scala"


def test_class_extending_a_trait_still_resolves_to_the_real_trait_node(tmp_path):
    """Guard against regressing the direction that already partially worked:
    a class's `extends TraitName` must still land on the trait's own node,
    not on some id it never had a reason to get."""
    f = _write(tmp_path / "src" / "Impl.scala",
               "package demo\n\n"
               "trait Api\n\n"
               "class Impl extends Api\n")
    r = extract([f], cache_root=tmp_path)
    inherits = {(_label_of(r, e["source"]), _label_of(r, e["target"])) for e in _edges(r, "inherits")}
    assert ("Impl", "Api") in inherits
    api = _node(r, "src/Impl.scala", "Api")
    assert api is not None and api["source_location"] == "L3"


def test_trait_member_field_and_method_attach_to_the_trait_not_the_file(tmp_path):
    """Secondary path: parent_class_nid propagation into a trait body.

    Before the fix a trait's members fell to the generic recurse branch,
    which resets parent_class_nid to None, so this val/def pair would have
    surfaced as if it belonged to the file, not to Repo.
    """
    f = _write(tmp_path / "src" / "Repo.scala",
               "package demo\n\n"
               "case class Settings(name: String)\n\n"
               "trait Repo {\n"
               "  val settings: Settings = Settings(\"default\")\n"
               "  def describe(): String = settings.name\n"
               "}\n")
    r = extract([f], cache_root=tmp_path)
    field_refs = {(_label_of(r, e["source"]), _label_of(r, e["target"]))
                  for e in _edges(r, "references") if e.get("context") == "field"}
    assert ("Repo", "Settings") in field_refs
    method_owners = _owners_of_relation(r, "method", "describe")
    assert method_owners == {"Repo"}


def test_distinct_named_trait_and_object_stay_independent(tmp_path):
    f = _write(tmp_path / "src" / "Pair.scala",
               "package demo\n\n"
               "trait Reader { def read(): String = \"r\" }\n"
               "object Writer { def write(): String = \"w\" }\n")
    r = extract([f], cache_root=tmp_path)
    reader = _node(r, "src/Pair.scala", "Reader")
    writer = _node(r, "src/Pair.scala", "Writer")
    assert reader is not None and writer is not None
    assert reader["id"] != writer["id"]
    assert _owners_of_relation(r, "method", "read") == {"Reader"}
    assert _owners_of_relation(r, "method", "write") == {"Writer"}


# ── Consumer secondary path: graphify affected traverses through a trait ───

def test_affected_traverses_mixes_in_edge_through_a_real_trait_node(tmp_path):
    f = _write(tmp_path / "src" / "Widget.scala",
               "package demo\n\n"
               "trait Base\n"
               "trait Loggable\n\n"
               "trait Widget extends Base with Loggable\n")
    r = extract([f], cache_root=tmp_path)
    graph = _to_digraph(r)
    loggable_id = _make_id(_file_stem(Path("src/Widget.scala")), "Loggable")
    hits = affected_nodes(graph, loggable_id, relations=("mixes_in", "inherits"), depth=2)
    assert any(_label_of(r, h.node_id) == "Widget" and h.via_relation == "mixes_in" for h in hits)


# ── Non-regression: cross-file companion resolution is untouched ───────────

def test_cross_file_reference_to_a_companion_pair_still_resolves_to_the_real_node(tmp_path):
    """Pins the specific behavior the maintainer's review flagged as broken
    by the (now-removed) collision guard: a reference in another file to a
    class + companion object pair must resolve to the real, sourced node,
    not to a dangling sourceless stub. This diff never touches id computation
    or `_rewire_unique_stub_nodes`, so this is v8's existing behavior,
    unchanged -- pinned directly rather than left implicit.
    """
    point = _write(tmp_path / "src" / "Point.scala",
                    "package demo\n\n"
                    "case class Point(x: Int, y: Int) { def norm(): Int = x + y }\n"
                    "object Point { def origin(): Point = Point(0, 0) }\n")
    path = _write(tmp_path / "src" / "Path.scala",
                   "package demo\n\n"
                   "class Path {\n"
                   "  def start(): Point = Point.origin()\n"
                   "}\n")
    r = extract([point, path], cache_root=tmp_path)
    point_nodes = [n for n in r["nodes"] if n["label"] == "Point"]
    assert len(point_nodes) == 1
    real_point = point_nodes[0]
    assert real_point["source_file"] == "src/Point.scala"

    start_return_type_targets = {
        e["target"] for e in _edges(r, "references")
        if e.get("context") == "return_type" and _label_of(r, e["source"]) == ".start()"
    }
    assert start_return_type_targets == {real_point["id"]}
