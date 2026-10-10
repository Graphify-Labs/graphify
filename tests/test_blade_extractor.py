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
