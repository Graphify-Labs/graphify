"""Extraction coverage for Laravel Blade templates."""
from __future__ import annotations

from graphify.extract import extract


def _edge_labels(result: dict, relation: str) -> set[tuple[str, str]]:
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    return {
        (labels.get(edge["source"], edge["source"]), labels.get(edge["target"], edge["target"]))
        for edge in result["edges"]
        if edge["relation"] == relation
    }


def test_blade_extends_links_view_to_its_layout(tmp_path):
    # @extends is template inheritance — the primary structural relationship in a
    # Blade view. Before the fix only @include was recognised, so a page that
    # extends a layout produced no edge to that layout at all.
    page = tmp_path / "page.blade.php"
    page.write_text(
        "@extends('layouts.app')\n"
        "@section('content')\n"
        "    @include('partials.nav')\n"
        "@endsection\n",
        encoding="utf-8",
    )

    result = extract([page], cache_root=tmp_path)

    assert ("page.blade.php", "layouts.app") in _edge_labels(result, "extends")
    # existing @include behaviour is preserved
    assert ("page.blade.php", "partials.nav") in _edge_labels(result, "includes")


def test_blade_wire_click_binds_the_bare_method_name(tmp_path):
    # wire:click="deleteItem(5)" bound to the literal argument-bearing text,
    # a node no real method ever matches — the call's own argument is not
    # part of the method's name.
    page = tmp_path / "page.blade.php"
    page.write_text(
        '<div wire:click="deleteItem(5)">Delete</div>\n'
        '<div wire:click="save">Save</div>\n',
        encoding="utf-8",
    )

    result = extract([page], cache_root=tmp_path)

    bindings = _edge_labels(result, "binds_method")
    assert ("page.blade.php", "deleteItem") in bindings
    assert ("page.blade.php", "save") in bindings


def test_blade_wire_click_with_a_modifier_is_still_bound(tmp_path):
    # wire:click.prevent="submit" never matched the bare wire:click= pattern
    # at all, so the binding silently vanished.
    page = tmp_path / "page.blade.php"
    page.write_text('<div wire:click.prevent="submit">Submit</div>\n', encoding="utf-8")

    result = extract([page], cache_root=tmp_path)

    assert ("page.blade.php", "submit") in _edge_labels(result, "binds_method")


def test_blade_wire_click_magic_action_is_not_bound(tmp_path):
    # $set/$emit/$toggle/$refresh are Livewire's own runtime actions, not a
    # method the component defines — binding one fabricates an edge to
    # something that does not exist.
    page = tmp_path / "page.blade.php"
    page.write_text("<div wire:click=\"$set('foo', 1)\">Reset</div>\n", encoding="utf-8")

    result = extract([page], cache_root=tmp_path)

    assert _edge_labels(result, "binds_method") == set()
