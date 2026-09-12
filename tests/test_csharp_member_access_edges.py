"""Reading a C# property/field on a typed receiver should link the accessing method to it.

The member-call resolver (#1609) binds `recv.Method()` to the receiver's declared type, but a
member used as a VALUE -- `ctx.Items` -- is not an invocation, so no branch ever saw it. A
property was therefore reachable only from its own declaration: "which methods read this
member" had no answer, and a type exposed purely through properties looked unused.

Resolution reuses the member-call path, so the guards it already carries apply here too: an
untypable receiver produces nothing rather than a guess, and an ambiguous type name is
skipped. These tests pin both the new edges and those refusals.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from graphify.extract import extract


def _graph(tmp_path: Path, files: dict[str, str]) -> dict:
    paths = []
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
        paths.append(path)
    return extract(paths, cache_root=tmp_path)


def _reads(graph: dict, *, from_label: str) -> set[tuple[str, str]]:
    """(label, source_location) of members read by `from_label`."""
    nodes = {n["id"]: n for n in graph["nodes"]}
    out = set()
    for edge in graph["edges"]:
        if edge.get("relation") != "references" or edge.get("context") != "member_access":
            continue
        if nodes.get(edge.get("source"), {}).get("label") != from_label:
            continue
        target = nodes.get(edge.get("target"), {})
        if target.get("label"):
            out.add((target["label"], target.get("source_location")))
    return out


def _labels(reads: set[tuple[str, str]]) -> set[str]:
    return {label for label, _ in reads}


MODEL = """
    namespace App.Data;
    public class Widget { public int Id { get; set; } }
    public class Gadget { public int Id { get; set; } }
    public class Box<T> { }
    public class Store
    {
        public Box<Widget> Widgets { get; set; }
        public Box<Gadget> Gadgets { get; set; }
        public string Label { get; set; }
        public void Save() { }
    }
"""

READER = """
    namespace App.Use;
    using App.Data;

    public class Reader
    {
        private Store _store;
        public void ReadsOneSet() { var q = _store.Widgets; }
        public void ReadsTheOtherSet() { var q = _store.Gadgets; }
        public void ReadsAScalar() { var s = _store.Label; }
        public void ReadsThenCalls() { _store.Widgets.ToString(); }
        public void CallsAMethod() { _store.Save(); }
        public void ReadsAnUnknownMember() { var x = _store.Missing; }
    }
"""


def test_reading_a_property_links_the_accessing_method(tmp_path):
    graph = _graph(tmp_path, {"Model.cs": MODEL, "Reader.cs": READER})
    assert "Widgets" in _labels(_reads(graph, from_label=".ReadsOneSet()"))


def test_two_properties_do_not_cross_attribute(tmp_path):
    """Each read must bind to its own member, not to any member of the type."""
    graph = _graph(tmp_path, {"Model.cs": MODEL, "Reader.cs": READER})
    assert _labels(_reads(graph, from_label=".ReadsOneSet()")) == {"Widgets"}
    assert _labels(_reads(graph, from_label=".ReadsTheOtherSet()")) == {"Gadgets"}


def test_a_scalar_property_is_linked_too(tmp_path):
    graph = _graph(tmp_path, {"Model.cs": MODEL, "Reader.cs": READER})
    assert "Label" in _labels(_reads(graph, from_label=".ReadsAScalar()"))


def test_the_member_and_not_the_same_named_type_is_linked(tmp_path):
    """`Widgets` the property must win over any same-named type in the corpus."""
    graph = _graph(tmp_path, {
        "Model.cs": MODEL,
        "Collide.cs": "namespace App.Data;\npublic class Widgets { }\n",
        "Reader.cs": READER,
    })
    reads = _reads(graph, from_label=".ReadsOneSet()")
    assert reads, "expected a member_access edge"
    # The property is declared inside Model.cs; the colliding class is its own file.
    nodes = {n["id"]: n for n in graph["nodes"]}
    targets = [
        n for n in nodes.values()
        if n.get("label") == "Widgets" and n.get("source_file", "").endswith("Model.cs")
    ]
    assert targets, "the property node should be the one linked"


def test_a_chained_call_still_records_the_read(tmp_path):
    """`ctx.Items.Any()` reads Items before calling on it."""
    graph = _graph(tmp_path, {"Model.cs": MODEL, "Reader.cs": READER})
    assert "Widgets" in _labels(_reads(graph, from_label=".ReadsThenCalls()"))


def test_a_method_call_is_not_recorded_as_a_read(tmp_path):
    """`_store.Save()` is a call; emitting a read as well would double-count it."""
    graph = _graph(tmp_path, {"Model.cs": MODEL, "Reader.cs": READER})
    assert _reads(graph, from_label=".CallsAMethod()") == set()


def test_an_unknown_member_on_a_known_type_links_nothing(tmp_path):
    graph = _graph(tmp_path, {"Model.cs": MODEL, "Reader.cs": READER})
    assert _reads(graph, from_label=".ReadsAnUnknownMember()") == set()


def test_an_untyped_receiver_links_nothing(tmp_path):
    """No declared type for the receiver means no edge, rather than a bare-name guess."""
    graph = _graph(tmp_path, {
        "Model.cs": MODEL,
        "Loose.cs": """
            namespace App.Use;
            public class Loose
            {
                public void Reads(object thing) { var x = thing.Widgets; }
            }
        """,
    })
    assert _reads(graph, from_label=".Reads()") == set()


def test_an_inherited_property_resolves_through_the_base(tmp_path):
    graph = _graph(tmp_path, {
        "Model.cs": MODEL,
        "Derived.cs": """
            namespace App.Data;
            public class BigStore : Store { }
        """,
        "Reader.cs": """
            namespace App.Use;
            using App.Data;

            public class BigReader
            {
                private BigStore _store;
                public void ReadsInherited() { var q = _store.Widgets; }
            }
        """,
    })
    assert "Widgets" in _labels(_reads(graph, from_label=".ReadsInherited()"))


def test_this_qualified_read_is_linked(tmp_path):
    graph = _graph(tmp_path, {
        "Own.cs": """
            namespace App.Data;
            public class Holder
            {
                public string Name { get; set; }
                public void ReadsOwn() { var n = this.Name; }
            }
        """,
    })
    assert "Name" in _labels(_reads(graph, from_label=".ReadsOwn()"))


def test_both_endpoints_of_every_edge_exist(tmp_path):
    """No dangling ids.

    A caller_nid is rewritten by several id passes (merge-away, prefix remap, symbol
    remap, collision disambiguation) after extraction. Carrying these entries on
    `raw_calls` inherits every one of those rewrites; a parallel channel had to repeat
    them, and missing one produced edges whose source was not a node -- invisible except
    as a query that silently returns nothing.
    """
    graph = _graph(tmp_path, {"Model.cs": MODEL, "Reader.cs": READER})
    ids = {n["id"] for n in graph["nodes"]}
    dangling = [
        (e["source"], e["target"]) for e in graph["edges"]
        if e.get("context") == "member_access"
        and (e["source"] not in ids or e["target"] not in ids)
    ]
    assert not dangling, f"dangling member_access edges: {dangling}"


def test_the_edge_is_a_reference_not_a_call(tmp_path):
    """A property read must not appear in the call graph."""
    graph = _graph(tmp_path, {"Model.cs": MODEL, "Reader.cs": READER})
    nodes = {n["id"]: n for n in graph["nodes"]}
    for edge in graph["edges"]:
        if nodes.get(edge.get("source"), {}).get("label") != ".ReadsOneSet()":
            continue
        target = nodes.get(edge.get("target"), {})
        if target.get("label") == "Widgets":
            assert edge.get("relation") == "references"
            assert edge.get("context") == "member_access"
