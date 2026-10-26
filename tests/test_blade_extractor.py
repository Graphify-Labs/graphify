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


def test_blade_x_component_tags_link_view_to_component(tmp_path):
    # <x-alert> / <x-forms.input> are anonymous Blade components. They were not
    # matched at all, so a view produced no edge to the components it renders and
    # shared components sat in the graph as isolated nodes.
    page = tmp_path / "page.blade.php"
    page.write_text(
        "<x-alert type=\"error\">Oops</x-alert>\n"
        "<x-forms.input name=\"email\" />\n"
        "<x-alert-banner/>\n",
        encoding="utf-8",
    )

    result = extract([page], cache_root=tmp_path)

    assert _edge_labels(result, "uses_component") == {
        ("page.blade.php", "x-alert"),
        ("page.blade.php", "x-forms.input"),
        ("page.blade.php", "x-alert-banner"),
    }


def test_blade_alpine_attributes_and_slots_are_not_components(tmp_path):
    # `x-` also prefixes Alpine attributes, and <x-slot> / <x-dynamic-component>
    # are Blade built-ins, not component files: none of them is a component use.
    page = tmp_path / "page.blade.php"
    page.write_text(
        "<div x-data=\"{ open: false }\" x-on:click=\"open = !open\" x-show=\"open\">\n"
        "    <x-slot name=\"header\">Title</x-slot>\n"
        "    <x-slot:footer>Footer</x-slot:footer>\n"
        "    <x-dynamic-component :component=\"$name\" />\n"
        "</div>\n",
        encoding="utf-8",
    )

    result = extract([page], cache_root=tmp_path)

    assert _edge_labels(result, "uses_component") == set()
    assert [n["label"] for n in result["nodes"]] == ["page.blade.php"]
