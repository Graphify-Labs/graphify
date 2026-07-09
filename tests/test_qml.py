"""Tests for the QML extractor: object trees, id references, embedded-JS calls."""
from __future__ import annotations

import importlib.util as _ilu
import tempfile
import textwrap
from pathlib import Path

import pytest

from graphify.extract import extract_qml

FIXTURES = Path(__file__).parent / "fixtures"

# tree-sitter-qmljs is an optional extra (the [qml] extra / dev group git pin) --
# skip gracefully for anyone who ran a bare `uv sync` without it.
_needs_qml = pytest.mark.skipif(
    _ilu.find_spec("tree_sitter_qmljs") is None,
    reason="tree-sitter-qmljs not installed (optional [qml] extra)",
)


def _write(tmp_path: Path, name: str, code: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(code), encoding="utf-8")
    return p


def _node(r, label):
    return next((n for n in r["nodes"] if n["label"] == label), None)


def _edges(r, relation=None):
    if relation is None:
        return r["edges"]
    return [e for e in r["edges"] if e["relation"] == relation]


def _label_by_id(r):
    return {n["id"]: n["label"] for n in r["nodes"]}


def _edge_labels(r, relation):
    by_id = _label_by_id(r)
    return {
        (by_id.get(e["source"], e["source"]), by_id.get(e["target"], e["target"]))
        for e in r["edges"] if e["relation"] == relation
    }


def _relations(r):
    return {e["relation"] for e in r["edges"]}


@_needs_qml
def test_qml_no_error_on_sample_fixture():
    r = extract_qml(FIXTURES / "sample.qml")
    assert r.get("error") is None
    assert r["nodes"]
    assert r["edges"]


@_needs_qml
def test_qml_file_and_component_nodes(tmp_path):
    path = _write(tmp_path, "Widget.qml", """
        Item {
            id: root
        }
    """)
    r = extract_qml(path)
    file_node = _node(r, "Widget.qml")
    assert file_node is not None
    assert file_node["source_file"] == str(path)

    # The root object is the file's own component, named after the file stem.
    component_node = _node(r, "Widget")
    assert component_node is not None
    assert component_node["source_file"] == str(path)
    assert (file_node["label"], component_node["label"]) in _edge_labels(r, "contains")


@_needs_qml
def test_qml_grouped_binding_is_not_a_child_object(tmp_path):
    """`anchors { ... }` and `font { ... }` are property groups, not real objects."""
    path = _write(tmp_path, "sample.qml", """
        Item {
            id: root
            anchors {
                left: parent.left
                right: parent.right
            }
            Text {
                id: label
                font {
                    pixelSize: 14
                }
            }
        }
    """)
    r = extract_qml(path)
    labels = [n["label"] for n in r["nodes"]]
    assert "anchors" not in labels
    assert "font" not in labels
    assert "label" in labels


@_needs_qml
def test_qml_behavior_on_produces_real_child_objects(tmp_path):
    """Unlike grouped bindings, `Behavior on <prop> { ... }` is always real."""
    path = _write(tmp_path, "sample.qml", """
        Item {
            id: root
            Behavior on width {
                NumberAnimation { duration: 120 }
            }
        }
    """)
    r = extract_qml(path)
    labels = [n["label"] for n in r["nodes"]]
    assert "Behavior" in labels
    assert "NumberAnimation" in labels
    contains = _edge_labels(r, "contains")
    # The root object's `id: root` is folded into the file's own component node
    # (named after the file stem, "sample"), not a separate "root" node.
    assert ("sample", "Behavior") in contains
    assert ("Behavior", "NumberAnimation") in contains


@_needs_qml
def test_qml_ids_become_nodes_keyed_by_id(tmp_path):
    """A non-root object's `id:` becomes its own node, keyed by that id."""
    path = _write(tmp_path, "sample.qml", """
        Item {
            id: root
            Text {
                id: label
                text: "hi"
            }
        }
    """)
    r = extract_qml(path)
    assert _node(r, "label") is not None
    # The root's `id: root` doesn't produce a separate "root" node -- it's
    # folded into the file's own component node (named "sample" after the
    # file stem). A reference to `root` should resolve there instead.
    assert _node(r, "root") is None
    assert _node(r, "sample") is not None


@_needs_qml
def test_qml_custom_component_gets_sourceless_stub(tmp_path):
    path = _write(tmp_path, "sample.qml", """
        Item {
            id: root
            CustomPanel {
                id: panel
            }
        }
    """)
    r = extract_qml(path)
    stub = _node(r, "CustomPanel")
    assert stub is not None
    assert stub["source_file"] == ""
    assert ("panel", "CustomPanel") in _edge_labels(r, "instantiates")


@_needs_qml
def test_qml_builtin_types_never_get_stubs(tmp_path):
    path = _write(tmp_path, "sample.qml", """
        Item {
            id: root
            Rectangle {
                id: box
            }
            ColumnLayout {
                id: col
            }
        }
    """)
    r = extract_qml(path)
    labels = [n["label"] for n in r["nodes"]]
    assert "Rectangle" not in labels
    assert "ColumnLayout" not in labels
    assert "instantiates" not in _relations(r)


@_needs_qml
def test_qml_member_call_does_not_cross_wire_same_named_methods(tmp_path):
    """`x.refresh()` must resolve to the `refresh` defined ON `x`, not just any
    same-named function elsewhere in the file. func_table is a flat,
    whole-file dict keyed only by name, so `other`'s `refresh()` (declared
    later) overwrites `root`'s entry -- without an owner check, calling
    `root.refresh()` would then wrongly resolve to `other`'s function.
    The safe behavior is: the receiver that actually owns the resolved
    function gets a `calls` edge, and the other gets none (rather than a
    wrong one)."""
    path = _write(tmp_path, "sample.qml", """
        Item {
            id: root
            function refresh() { }

            Item {
                id: other
                function refresh() { }
            }

            CustomPanel {
                id: panelA
                onClicked: other.refresh()
            }
            CustomPanel {
                id: panelB
                onPressed: root.refresh()
            }
        }
    """)
    r = extract_qml(path)
    by_id = _label_by_id(r)
    other_refresh_nid = next(
        e["target"] for e in _edges(r, "defines")
        if by_id.get(e["source"]) == "other" and by_id.get(e["target"]) == "refresh()"
    )
    calls = {(by_id.get(e["source"]), e["target"]) for e in _edges(r, "calls")}
    assert ("panelA", other_refresh_nid) in calls
    # root.refresh() must NOT resolve to other's refresh() -- no wrong edge.
    assert ("panelB", other_refresh_nid) not in calls


@_needs_qml
def test_qml_anonymous_siblings_on_same_line_stay_distinct(tmp_path):
    """Two same-typed, id-less siblings starting on the same source line must
    not collapse into a single node (a line-only fallback id would merge them)."""
    path = _write(tmp_path, "sample.qml", """
        Item {
            id: root
            states: [ State { name: "a" }, State { name: "b" } ]
        }
    """)
    r = extract_qml(path)
    state_ids = {n["id"] for n in r["nodes"] if n["label"] == "State"}
    assert len(state_ids) == 2, f"expected 2 distinct State nodes, got {state_ids}"


@_needs_qml
def test_qml_bare_function_reference_without_call_parens(tmp_path):
    """`onClicked: doSomething` (no call parens, function assigned by
    reference) must still produce an edge to the function, not silently drop it."""
    path = _write(tmp_path, "sample.qml", """
        Item {
            id: root
            function doSomething() { }
            CustomPanel {
                id: panel
                onClicked: doSomething
            }
        }
    """)
    r = extract_qml(path)
    do_something = _node(r, "doSomething()")
    assert do_something is not None
    refs = _edges(r, "references")
    assert any(e["target"] == do_something["id"] for e in refs)


@_needs_qml
def test_qml_property_alias_references_target_id(tmp_path):
    path = _write(tmp_path, "sample.qml", """
        Item {
            id: root
            property alias labelText: label.text
            Text {
                id: label
                text: "hi"
            }
        }
    """)
    r = extract_qml(path)
    alias_node = _node(r, "labelText")
    label_node = _node(r, "label")
    assert alias_node is not None and label_node is not None
    refs = _edges(r, "references")
    assert any(e["source"] == alias_node["id"] and e["target"] == label_node["id"] for e in refs)


@_needs_qml
def test_qml_function_calls_local_function(tmp_path):
    path = _write(tmp_path, "sample.qml", """
        Item {
            id: root
            function refresh() {
                helper()
            }
            function helper() {}
        }
    """)
    r = extract_qml(path)
    calls = _edge_labels(r, "calls")
    assert ("refresh()", "helper()") in calls


@_needs_qml
def test_qml_event_handler_calls_and_references(tmp_path):
    path = _write(tmp_path, "sample.qml", """
        Item {
            id: root
            function refresh() {}
            CustomPanel {
                id: panel
                onClicked: root.refresh()
            }
        }
    """)
    r = extract_qml(path)
    by_id = _label_by_id(r)
    # `root`'s id: root folds into the file's own component node ("sample").
    event_refs = [
        e for e in _edges(r, "references")
        if e.get("context") == "event" and by_id.get(e["target"]) == "sample"
    ]
    assert event_refs, "expected an event-context reference edge from the handler to `root` (the component node)"
    assert ("panel", "refresh()") in _edge_labels(r, "calls")


@_needs_qml
def test_qml_object_array_children_are_real_objects(tmp_path):
    """`states: [ State { ... } ]` -- children of a `ui_object_array` value are real objects."""
    path = _write(tmp_path, "sample.qml", """
        Item {
            id: root
            states: [
                State { name: "open" },
                State { name: "closed" }
            ]
        }
    """)
    r = extract_qml(path)
    labels = [n["label"] for n in r["nodes"]]
    assert labels.count("State") == 2


@_needs_qml
def test_qml_imports_produce_imports_from_edges(tmp_path):
    path = _write(tmp_path, "sample.qml", """
        import QtQuick 2.15
        import "../common" as CommonJs

        Item {
            id: root
        }
    """)
    r = extract_qml(path)
    imports = _edge_labels(r, "imports_from")
    assert ("sample.qml", "QtQuick") in imports
    assert ("sample.qml", "common") in imports


@_needs_qml
def test_qml_inline_component(tmp_path):
    path = _write(tmp_path, "sample.qml", """
        Item {
            id: root
            component InlineBadge: Rectangle {
                id: badge
                color: "red"
                function paint() {}
            }
            CustomUser {
                target: badge
            }
        }
    """)
    r = extract_qml(path)
    badge_node = _node(r, "InlineBadge")
    assert badge_node is not None
    # `id: badge` on the inline component's own object folds into the
    # InlineBadge node (same convention as the file-root object), rather than
    # creating a separate "badge" node.
    assert _node(r, "badge") is None
    assert _node(r, "paint()") is not None
    contains = _edge_labels(r, "contains")
    assert ("sample", "InlineBadge") in contains
    assert ("InlineBadge", "paint()") in _edge_labels(r, "defines")
    # A reference elsewhere in the file to `badge` resolves onto InlineBadge.
    refs = _edges(r, "references")
    assert any(e["target"] == badge_node["id"] for e in refs)


@_needs_qml
def test_qml_missing_grammar_reports_error(monkeypatch, tmp_path):
    """When tree-sitter-qmljs isn't installed, extract_qml degrades to an explicit error, not a crash."""
    import graphify.extractors.qml as qmlmod
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "tree_sitter_qmljs":
            raise ImportError("no module named tree_sitter_qmljs")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    path = _write(tmp_path, "sample.qml", "Item { id: root }")
    r = qmlmod.extract_qml(path)
    assert r["nodes"] == []
    assert r["edges"] == []
    assert r.get("error")
