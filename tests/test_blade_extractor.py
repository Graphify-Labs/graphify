"""Extraction coverage for Laravel Blade templates."""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

import networkx as nx
import pytest

from graphify.affected import DEFAULT_AFFECTED_RELATIONS, affected_nodes
from graphify.build import build_from_json
from graphify.extract import extract
from graphify.extractors import blade
from graphify.extractors.blade import refresh_blade_paths, resolve_blade_references


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


# ── Target resolution: edges land on the real view / component file node ──────


def _write(root: Path, rel: str, body: str = "<div></div>\n") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _extract(root: Path, paths: list[Path] | None = None, **kwargs) -> dict:
    return extract(
        sorted(root.rglob("*.blade.php")) if paths is None else paths,
        root=root, cache_root=kwargs.pop("cache_root", root), parallel=False, **kwargs,
    )


def _file_id(result: dict, rel: str) -> str:
    [nid] = [n["id"] for n in result["nodes"]
             if n["source_file"] == rel and n["label"] == PurePosixPath(rel).name]
    return nid


def _targets(result: dict, source_rel: str, relation: str) -> list[str]:
    source = _file_id(result, source_rel)
    return [e["target"] for e in result.get("links", result.get("edges", []))
            if e["source"] == source and e["relation"] == relation]


def _labels(result: dict) -> set[str]:
    return {n["label"] for n in result["nodes"]}


def _assert_integrity(result: dict) -> None:
    ids = {n["id"] for n in result["nodes"]}
    for e in result.get("links", result.get("edges", [])):
        assert e["source"] in ids, e
        assert e["target"] in ids, e


def _assert_no_blade_markers(result: dict) -> None:
    for item in [*result["nodes"], *result.get("links", result.get("edges", []))]:
        assert not [k for k in item if k.startswith("_blade")], item


def test_blade_component_edge_targets_the_component_file_node(tmp_path):
    # The bug: the edge pointed at an `x-layout` stub, so the layout's own file
    # node never had an incoming edge. Assert on ids, not labels.
    _write(tmp_path, "resources/views/components/layout.blade.php", "<div>{{ $slot }}</div>")
    _write(tmp_path, "resources/views/pages/home.blade.php", "<x-layout>hi</x-layout>")

    result = _extract(tmp_path)

    layout = _file_id(result, "resources/views/components/layout.blade.php")
    assert _targets(result, "resources/views/pages/home.blade.php", "uses_component") == [layout]
    assert "x-layout" not in _labels(result)  # the orphaned stub is dropped
    _assert_integrity(result)
    _assert_no_blade_markers(result)


def test_blade_nested_component_name_maps_to_subdirectory(tmp_path):
    _write(tmp_path, "resources/views/components/forms/input.blade.php")
    _write(tmp_path, "resources/views/page.blade.php", '<x-forms.input name="email" />')

    result = _extract(tmp_path)

    assert _targets(result, "resources/views/page.blade.php", "uses_component") == [
        _file_id(result, "resources/views/components/forms/input.blade.php")]


def test_blade_component_falls_back_to_index_file(tmp_path):
    _write(tmp_path, "resources/views/components/accordion/index.blade.php")
    _write(tmp_path, "resources/views/page.blade.php", "<x-accordion>...</x-accordion>")

    result = _extract(tmp_path)

    assert _targets(result, "resources/views/page.blade.php", "uses_component") == [
        _file_id(result, "resources/views/components/accordion/index.blade.php")]


def test_blade_component_file_wins_over_index_file(tmp_path):
    # Laravel looks up components/foo.blade.php before components/foo/index.blade.php.
    _write(tmp_path, "resources/views/components/foo.blade.php")
    _write(tmp_path, "resources/views/components/foo/index.blade.php")
    _write(tmp_path, "resources/views/page.blade.php", "<x-foo/>")

    result = _extract(tmp_path)

    assert _targets(result, "resources/views/page.blade.php", "uses_component") == [
        _file_id(result, "resources/views/components/foo.blade.php")]


def test_blade_include_and_extends_target_the_view_file_nodes(tmp_path):
    _write(tmp_path, "resources/views/layouts/app.blade.php", "@yield('content')")
    _write(tmp_path, "resources/views/partials/nav.blade.php", "<nav></nav>")
    _write(tmp_path, "resources/views/home.blade.php",
           "@extends('layouts.app')\n@section('content')\n@include('partials.nav')\n@endsection\n")
    _write(tmp_path, "resources/views/about.blade.php", "@include(\"partials/nav\")")

    result = _extract(tmp_path)

    nav = _file_id(result, "resources/views/partials/nav.blade.php")
    assert _targets(result, "resources/views/home.blade.php", "extends") == [
        _file_id(result, "resources/views/layouts/app.blade.php")]
    assert _targets(result, "resources/views/home.blade.php", "includes") == [nav]
    assert _targets(result, "resources/views/about.blade.php", "includes") == [nav]
    assert not {"layouts.app", "partials.nav", "partials/nav"} & _labels(result)
    _assert_integrity(result)


def test_blade_resolves_below_a_scan_root_above_the_laravel_root(tmp_path):
    _write(tmp_path, "backend/resources/views/components/card.blade.php")
    _write(tmp_path, "backend/resources/views/page.blade.php", "<x-card/>")

    result = _extract(tmp_path)

    assert _targets(result, "backend/resources/views/page.blade.php", "uses_component") == [
        _file_id(result, "backend/resources/views/components/card.blade.php")]


def test_blade_missing_target_keeps_the_stub(tmp_path):
    # Fail closed: nothing to resolve to, so the pre-resolution stub edge stays.
    _write(tmp_path, "resources/views/page.blade.php",
           "<x-ghost/>\n@include('partials.missing')\n@extends('layouts.gone')\n")

    result = _extract(tmp_path)

    assert ("page.blade.php", "x-ghost") in _edge_labels(result, "uses_component")
    assert ("page.blade.php", "partials.missing") in _edge_labels(result, "includes")
    assert ("page.blade.php", "layouts.gone") in _edge_labels(result, "extends")
    stubs = [n for n in result["nodes"] if n["label"] in ("x-ghost", "partials.missing")]
    assert len(stubs) == 2
    assert all(n["source_file"] == "resources/views/page.blade.php" for n in stubs)
    _assert_integrity(result)
    _assert_no_blade_markers(result)


def test_blade_ambiguous_target_keeps_the_stub(tmp_path):
    # Two Laravel apps in one corpus both define the component: never guess.
    _write(tmp_path, "apps/a/resources/views/components/card.blade.php")
    _write(tmp_path, "apps/b/resources/views/components/card.blade.php")
    _write(tmp_path, "apps/a/resources/views/page.blade.php", "<x-card/>")

    result = _extract(tmp_path)

    assert ("page.blade.php", "x-card") in _edge_labels(result, "uses_component")
    for rel in ("apps/a/resources/views/components/card.blade.php",
                "apps/b/resources/views/components/card.blade.php"):
        assert not any(e["target"] == _file_id(result, rel) for e in result["edges"])


def test_blade_ambiguous_component_file_does_not_fall_through_to_index(tmp_path):
    # The higher-priority candidate is ambiguous; picking the index file instead
    # would be a guess Laravel never makes.
    _write(tmp_path, "apps/a/resources/views/components/foo.blade.php")
    _write(tmp_path, "apps/b/resources/views/components/foo.blade.php")
    _write(tmp_path, "apps/a/resources/views/components/foo/index.blade.php")
    _write(tmp_path, "apps/a/resources/views/page.blade.php", "<x-foo/>")

    result = _extract(tmp_path)

    assert ("page.blade.php", "x-foo") in _edge_labels(result, "uses_component")


def test_blade_namespaced_views_and_components_stay_unresolved(tmp_path):
    # `pkg::view` names a package/vendor view; resolving it from the bare name
    # would bind it to an unrelated application file that happens to match.
    _write(tmp_path, "resources/views/html/button.blade.php")
    _write(tmp_path, "resources/views/components/message.blade.php")
    _write(tmp_path, "resources/views/page.blade.php",
           "@include('mail::html.button')\n<x-mail::message>Hi</x-mail::message>\n")

    result = _extract(tmp_path)

    assert ("page.blade.php", "mail::html.button") in _edge_labels(result, "includes")
    assert ("page.blade.php", "x-mail::message") in _edge_labels(result, "uses_component")


def _resolution_corpus(root: Path) -> None:
    _write(root, "resources/views/layouts/app.blade.php", "@yield('content')")
    _write(root, "resources/views/components/layout.blade.php")
    _write(root, "resources/views/components/forms/input.blade.php")
    _write(root, "resources/views/partials/nav.blade.php")
    _write(root, "resources/views/home.blade.php",
           "@extends('layouts.app')\n@include('partials.nav')\n<x-layout><x-forms.input/>"
           "<x-ghost/></x-layout>\n")
    _write(root, "resources/views/about.blade.php", "@include('partials.nav')\n<x-ghost/>\n")


def _edge_set(result: dict) -> set[tuple[str, str, str]]:
    return {(e["source"], e["target"], e["relation"]) for e in result["edges"]}


def test_blade_resolution_is_deterministic(tmp_path):
    root = tmp_path / "repo"
    _resolution_corpus(root)
    paths = sorted(root.rglob("*.blade.php"))
    first = _extract(root, paths, cache_root=tmp_path / "c1")
    cached = _extract(root, paths, cache_root=tmp_path / "c1")
    shuffled = list(paths)
    random.Random(4242).shuffle(shuffled)
    reordered = _extract(root, shuffled, cache_root=tmp_path / "c2")
    reversed_ = _extract(root, paths[::-1], cache_root=tmp_path / "c3")

    for other in (cached, reordered, reversed_):
        assert _edge_set(other) == _edge_set(first)
        assert {n["id"] for n in other["nodes"]} == {n["id"] for n in first["nodes"]}
    assert _targets(first, "resources/views/home.blade.php", "includes") == [
        _file_id(first, "resources/views/partials/nav.blade.php")]


def test_blade_resolver_matches_windows_paths(monkeypatch):
    # Windows source_files carry backslashes; matching goes through as_posix(),
    # never a raw string comparison or a split on a separator.
    monkeypatch.setattr(blade, "Path", PureWindowsPath)
    home = {"id": "home", "label": "home.blade.php", "file_type": "code",
            "source_file": r"C:\proj\resources\views\home.blade.php", "source_location": None}
    layout = {"id": "layout", "label": "layout.blade.php", "file_type": "code",
              "source_file": r"C:\proj\resources\views\components\layout.blade.php",
              "source_location": None}
    stub = {"id": "components_layout", "label": "x-layout", "file_type": "code",
            "source_file": home["source_file"], "source_location": None, "_blade_stub": True}
    edge = {"source": "home", "target": "components_layout", "relation": "uses_component",
            "source_file": home["source_file"],
            "_blade_ref": {"kind": "component", "name": "layout"}}
    nodes, edges = [home, layout, stub], [edge]

    resolve_blade_references([{"nodes": [home, stub]}, {"nodes": [layout]}], nodes, edges)

    assert edge["target"] == "layout"
    assert "_blade_ref" not in edge
    assert nodes == [home, layout]


def test_blade_changed_view_resolves_against_unchanged_target(tmp_path):
    # Incremental rebuild: only the view is re-extracted; the component it uses
    # comes from the persisted graph as read-only resolution context.
    _resolution_corpus(tmp_path)
    full = _extract(tmp_path)
    home = tmp_path / "resources/views/home.blade.php"
    home.write_text("<x-layout>changed</x-layout>\n", encoding="utf-8")

    changed = _extract(tmp_path, [home],
                       resolution_context_nodes=full["nodes"],
                       resolution_context_edges=full["edges"])

    layout = _file_id(full, "resources/views/components/layout.blade.php")
    assert _targets(changed, "resources/views/home.blade.php", "uses_component") == [layout]
    # The scratch-list run must still drop the orphaned stub from the real result.
    assert "x-layout" not in _labels(changed)
    assert layout not in {n["id"] for n in changed["nodes"]}  # context is never returned
    _assert_no_blade_markers(changed)


def test_blade_refresh_paths_widens_only_on_blade_set_changes(tmp_path):
    views = [tmp_path / "resources/views/a.blade.php", tmp_path / "resources/views/b.blade.php"]
    php = tmp_path / "app/Models/User.php"
    corpus = [php, *views]

    unchanged = [php]
    assert refresh_blade_paths(unchanged, corpus) is unchanged
    assert refresh_blade_paths([views[0]], corpus) == views
    deleted = tmp_path / "resources/views/components/card.blade.php"
    assert refresh_blade_paths([php], corpus, [deleted]) == [php, *views]
    assert refresh_blade_paths([tmp_path / ".graphifyignore"], corpus) == [
        tmp_path / ".graphifyignore", *views]


@pytest.mark.parametrize("mode", ["watch", "cli"])
def test_blade_incremental_target_addition_and_deletion(tmp_path, monkeypatch, mode):
    # An UNCHANGED view must follow its target appearing and disappearing.
    root = tmp_path / "repo"
    home = _write(root, "resources/views/home.blade.php", "<x-card/>\n")
    _write(root, "resources/views/about.blade.php", "<p>about</p>\n")
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[1]))
    monkeypatch.chdir(root)

    def rebuild(changed=None):
        if mode == "watch":
            from graphify.watch import _rebuild_code
            assert _rebuild_code(root, changed_paths=changed, acquire_lock=False,
                                 no_cluster=True)
        else:
            p = subprocess.run(
                [sys.executable, "-m", "graphify", "extract", str(root), "--code-only",
                 "--no-cluster"],
                cwd=root, env=os.environ.copy(), capture_output=True, text=True,
            )
            assert p.returncode == 0, p.stdout + p.stderr
        result = json.loads((root / "graphify-out/graph.json").read_text())
        _assert_integrity(result)
        _assert_no_blade_markers(result)
        return result

    def card_targets(result):
        return _targets(result, "resources/views/home.blade.php", "uses_component")

    first = rebuild()
    [stub] = card_targets(first)
    assert stub not in {n["id"] for n in first["nodes"] if n["label"].endswith(".blade.php")}

    card = _write(root, "resources/views/components/card.blade.php")
    added = rebuild([card])
    assert card_targets(added) == [_file_id(added, "resources/views/components/card.blade.php")]
    assert "x-card" not in _labels(added)

    home.write_text("<x-card>edited</x-card>\n", encoding="utf-8")
    edited = rebuild([home])
    assert card_targets(edited) == [_file_id(edited, "resources/views/components/card.blade.php")]

    card.unlink()
    removed = rebuild([card])
    assert card_targets(removed) == [stub]
    assert "x-card" in _labels(removed)


# ── affected: blast radius follows Blade relations ─────────────────────────────


def test_affected_follows_blade_includes_and_components():
    g = nx.DiGraph()
    for nid in ("home", "about", "layout", "nav"):
        g.add_node(nid, label=f"{nid}.blade.php", source_file=f"resources/views/{nid}.blade.php")
    g.add_edge("home", "layout", relation="uses_component")
    g.add_edge("about", "nav", relation="includes")

    assert {"includes", "uses_component"} <= set(DEFAULT_AFFECTED_RELATIONS)
    assert {h.node_id for h in affected_nodes(g, "layout")} == {"home"}
    assert {h.node_id for h in affected_nodes(g, "nav")} == {"about"}


def test_affected_reaches_the_view_that_uses_a_component(tmp_path):
    _write(tmp_path, "resources/views/components/layout.blade.php", "<div>{{ $slot }}</div>")
    _write(tmp_path, "resources/views/pages/home.blade.php", "<x-layout>hi</x-layout>")
    result = _extract(tmp_path)
    G = build_from_json(result, directed=True)

    layout = _file_id(result, "resources/views/components/layout.blade.php")
    home = _file_id(result, "resources/views/pages/home.blade.php")
    assert [h.node_id for h in affected_nodes(G, layout)] == [home]


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
