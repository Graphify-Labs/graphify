"""Unit tests for the Swift module symbol table and lexical type lookup."""
from __future__ import annotations

from graphify.extractors.resolution import (
    SwiftTypeIndex,
    _swift_lookup,
    _swift_type_index,
)


def _node(nid: str, qualified: list[str], source_file: str = "App/Model.swift", **extra) -> dict:
    return {
        "id": nid,
        "label": qualified[0].rsplit(".", 1)[-1],
        "source_file": source_file,
        "_swift_qualified": qualified,
        **extra,
    }


def test_index_keys_by_path_and_last_segment():
    index = _swift_type_index([
        _node("layout", ["Layout"]),
        _node("pane", ["Layout.Pane"]),
    ])
    assert isinstance(index, SwiftTypeIndex)
    assert index.by_path == {"Layout": ["layout"], "Layout.Pane": ["pane"]}
    assert index.by_label == {"Layout": ["layout"], "Pane": ["pane"]}


def test_extension_only_nodes_are_excluded():
    index = _swift_type_index([
        _node("view", ["View"], _swift_extension_only=True),
        _node("real", ["Real"]),
    ])
    assert "View" not in index.by_path
    assert "View" not in index.by_label
    assert _swift_lookup(index, "View", "") == ("external", None)


def test_non_swift_nodes_are_excluded():
    index = _swift_type_index([
        _node("py_cls", ["Config"], source_file="app/config.py"),
        _node("m_cls", ["Config"], source_file="app/Config.m"),
        {"id": "plain", "label": "Plain", "source_file": "App/Plain.swift"},
    ])
    assert index.by_path == {}
    assert index.by_label == {}


def test_lexical_lookup_is_innermost_first():
    index = _swift_type_index([
        _node("top_state", ["State"]),
        _node("feature_state", ["Feature.State"]),
        _node("inner_state", ["Feature.Sub.State"]),
        _node("feature", ["Feature"]),
        _node("sub", ["Feature.Sub"]),
    ])
    assert _swift_lookup(index, "State", "Feature.Sub") == ("resolved", "inner_state")
    assert _swift_lookup(index, "State", "Feature") == ("resolved", "feature_state")
    assert _swift_lookup(index, "State", "") == ("resolved", "top_state")
    assert _swift_lookup(index, "State", "Other") == ("resolved", "top_state")


def test_dotted_name_resolves_through_scope_levels():
    index = _swift_type_index([
        _node("layout", ["Layout"]),
        _node("pane", ["Layout.Pane"]),
    ])
    assert _swift_lookup(index, "Layout.Pane", "") == ("resolved", "pane")
    assert _swift_lookup(index, "Layout.Pane", "Screen") == ("resolved", "pane")
    assert _swift_lookup(index, "Pane", "Layout") == ("resolved", "pane")


def test_two_candidates_at_a_level_stop_the_search():
    index = _swift_type_index([
        _node("a_cfg", ["Feature.Config"], source_file="A.swift"),
        _node("b_cfg", ["Feature.Config"], source_file="B.swift"),
        _node("top_cfg", ["Config"]),
    ])
    # The Feature level has 2 candidates; the outer Config must not win.
    assert _swift_lookup(index, "Config", "Feature") == ("ambiguous", None)
    # Outside Feature the top-level Config is the only candidate.
    assert _swift_lookup(index, "Config", "") == ("resolved", "top_cfg")


def test_nested_type_is_unresolved_outside_its_scope():
    index = _swift_type_index([
        _node("outer", ["Outer"]),
        _node("outer_config", ["Outer.Config"]),
    ])
    assert _swift_lookup(index, "Config", "") == ("unresolved", None)
    assert _swift_lookup(index, "Config", "Other") == ("unresolved", None)
    assert _swift_lookup(index, "Config", "Outer") == ("resolved", "outer_config")


def test_unknown_last_segment_is_external():
    index = _swift_type_index([_node("pane", ["Layout.Pane"])])
    assert _swift_lookup(index, "View", "Layout") == ("external", None)
    assert _swift_lookup(index, "SwiftUI.View", "") == ("external", None)
    assert _swift_lookup(index, "", "") == ("external", None)


def test_dotted_name_with_known_last_segment_but_wrong_path_is_unresolved():
    index = _swift_type_index([_node("pane", ["Layout.Pane"])])
    assert _swift_lookup(index, "Other.Pane", "Layout") == ("unresolved", None)


def test_node_with_two_paths_is_ambiguous_whenever_hit():
    index = _swift_type_index([
        _node("state", ["A.State", "B.State"]),
    ])
    assert index.by_path["A.State"] == ["state"]
    assert index.by_path["B.State"] == ["state"]
    assert _swift_lookup(index, "State", "A") == ("ambiguous", None)
    assert _swift_lookup(index, "A.State", "") == ("ambiguous", None)
    assert _swift_lookup(index, "B.State", "Elsewhere") == ("ambiguous", None)
    assert _swift_lookup(index, "State", "") == ("unresolved", None)


def test_two_paths_with_different_last_segments_are_ambiguous():
    # Caseless ids fold `struct Config` and `enum CONFIG` onto one node.
    index = _swift_type_index([_node("same", ["A.Foo", "B.FOO"])])
    assert _swift_lookup(index, "A.Foo", "") == ("ambiguous", None)
    assert _swift_lookup(index, "B.FOO", "") == ("ambiguous", None)
    assert _swift_lookup(index, "Foo", "A") == ("ambiguous", None)
    assert _swift_lookup(index, "FOO", "B") == ("ambiguous", None)


def test_same_node_listed_twice_is_one_candidate():
    node = _node("pane", ["Layout.Pane"])
    index = _swift_type_index([node, dict(node)])
    assert index.by_path == {"Layout.Pane": ["pane"]}
    assert _swift_lookup(index, "Pane", "Layout") == ("resolved", "pane")


def test_order_is_deterministic_regardless_of_input_order():
    nodes = [
        _node("c", ["X.T"]),
        _node("a", ["X.T"]),
        _node("b", ["Y.T"]),
    ]
    forward = _swift_type_index(nodes)
    backward = _swift_type_index(list(reversed(nodes)))
    assert forward == backward
    assert forward.by_path["X.T"] == ["a", "c"]
    assert forward.by_label["T"] == ["a", "b", "c"]
    assert _swift_lookup(forward, "T", "X") == _swift_lookup(backward, "T", "X") == ("ambiguous", None)
