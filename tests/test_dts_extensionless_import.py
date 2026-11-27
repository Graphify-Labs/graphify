"""Extensionless TypeScript imports resolve to declaration files (#5472)."""
import json
from pathlib import Path

import networkx as nx
import pytest

from graphify.build import build_from_json
from graphify.extract import extract
from graphify.extractors.resolution import (
    _resolve_js_import_path,
    _resolve_workspace_import,
)


def importer_edges(result, source_file):
    return [
        edge for edge in result["edges"]
        if edge.get("source_file") == source_file
        and edge.get("relation") == "imports_from"
    ]


def file_node(result, source_file):
    return next(
        node for node in result["nodes"]
        if node.get("source_file") == source_file
        and node.get("label") == Path(source_file).name
    )


def test_issue_alias_and_relative_imports_reach_affected_cli(
    tmp_path, monkeypatch, capsys
):
    (tmp_path / "src/types").mkdir(parents=True)
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions":{"baseUrl":".","paths":{"#app/*":'
        '["src/*"]}}}',
        encoding="utf-8",
    )
    declaration = tmp_path / "src/types/api.d.ts"
    declaration.write_text("export interface Api { id: string }\n", encoding="utf-8")
    alias_importer = tmp_path / "src/view.ts"
    alias_importer.write_text("import type { Api } from '#app/types/api';\n")
    relative_importer = tmp_path / "src/rel.ts"
    relative_importer.write_text("import type { Api } from './types/api';\n")

    result = extract(
        [alias_importer, relative_importer, declaration],
        root=tmp_path,
        parallel=False,
    )
    target = file_node(result, "src/types/api.d.ts")["id"]
    for source in ("src/view.ts", "src/rel.ts"):
        assert [edge["target"] for edge in importer_edges(result, source)] == [target]

    graph = build_from_json(result, directed=True, root=tmp_path, dedup=False)
    for source in ("src/view.ts", "src/rel.ts"):
        source_id = file_node(result, source)["id"]
        graph_edges = graph.get_edge_data(source_id, target)
        assert graph_edges is not None
        assert graph_edges.get("relation") == "imports_from"
    graph_path = tmp_path / "graphify-out/graph.json"
    graph_path.parent.mkdir()
    graph_path.write_text(
        json.dumps(nx.node_link_data(graph, edges="links")), encoding="utf-8"
    )
    import graphify.__main__ as cli

    monkeypatch.setattr(cli, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "graphify",
            "affected",
            "src/types/api.d.ts",
            "--relation",
            "imports_from",
            "--graph",
            str(graph_path),
        ],
    )
    cli.main()
    output = capsys.readouterr().out
    assert "view.ts" in output
    assert "rel.ts" in output


@pytest.mark.parametrize("ext", [".ts", ".tsx", ".js", ".mjs", ".svelte"])
def test_existing_implementation_keeps_precedence(tmp_path, ext):
    candidate = tmp_path / "api"
    implementation = tmp_path / f"api{ext}"
    declaration = tmp_path / "api.d.ts"
    implementation.touch()
    declaration.touch()

    assert _resolve_js_import_path(candidate) == implementation


def test_directory_index_keeps_precedence_over_sibling_declaration(tmp_path):
    directory = tmp_path / "api"
    directory.mkdir()
    index = directory / "index.ts"
    declaration = tmp_path / "api.d.ts"
    index.touch()
    declaration.touch()

    assert _resolve_js_import_path(directory) == index


def test_named_type_import_reaches_declaration_symbol(tmp_path):
    (tmp_path / "src").mkdir()
    importer = tmp_path / "src/entry.ts"
    declaration = tmp_path / "src/api.d.ts"
    importer.write_text("import type { Api } from './api';\n")
    declaration.write_text("export interface Api {}\n")
    result = extract([importer, declaration], root=tmp_path, parallel=False)
    target_file = file_node(result, "src/api.d.ts")["id"]

    assert any(
        edge.get("relation") == "imports" and edge.get("target") == f"{target_file}_api"
        for edge in result["edges"]
        if edge.get("source_file") == "src/entry.ts"
    )


def test_declaration_directory_index_resolves(tmp_path):
    directory = tmp_path / "api"
    directory.mkdir()
    declaration_index = directory / "index.d.ts"
    declaration_index.touch()

    assert _resolve_js_import_path(directory) == declaration_index


def test_missing_import_stays_external(tmp_path):
    (tmp_path / "src").mkdir()
    importer = tmp_path / "src/entry.ts"
    importer.write_text("import type { Api } from './missing';\n")
    result = extract([importer], root=tmp_path, parallel=False)

    assert importer_edges(result, "src/entry.ts")[0]["target"].startswith("ref_")


def test_explicit_js_specifier_does_not_resolve_to_declaration(tmp_path):
    (tmp_path / "src").mkdir()
    importer = tmp_path / "src/entry.ts"
    declaration = tmp_path / "src/api.d.ts"
    importer.write_text("import './api.js';\n")
    declaration.touch()
    result = extract([importer, declaration], root=tmp_path, parallel=False)

    assert importer_edges(result, "src/entry.ts")[0]["target"] == "ref_api_js"


def test_dynamic_import_links_to_declaration(tmp_path):
    (tmp_path / "src").mkdir()
    importer = tmp_path / "src/entry.ts"
    declaration = tmp_path / "src/api.d.ts"
    importer.write_text("export async function load() { return import('./api'); }\n")
    declaration.touch()
    result = extract([importer, declaration], root=tmp_path, parallel=False)
    target = file_node(result, "src/api.d.ts")["id"]

    assert any(
        edge.get("deferred") and edge["target"] == target
        for edge in importer_edges(result, "src/entry.ts")
    )


@pytest.mark.parametrize("main", ["./lib/index", "./lib"])
def test_workspace_source_wins_over_declaration_fallback(tmp_path, main):
    (tmp_path / "apps/app").mkdir(parents=True)
    package = tmp_path / "packages/lib"
    (package / "lib").mkdir(parents=True)
    (package / "src").mkdir()
    (tmp_path / "package.json").write_text(
        '{"workspaces":["apps/*","packages/*"]}', encoding="utf-8"
    )
    (package / "package.json").write_text(
        json.dumps({"name": "@demo/lib", "main": main}), encoding="utf-8"
    )
    declaration = package / "lib/index.d.ts"
    source = package / "src/index.ts"
    declaration.touch()
    source.touch()

    assert _resolve_workspace_import("@demo/lib", tmp_path / "apps/app") == source


def test_workspace_declaration_is_used_when_there_is_no_source(tmp_path):
    (tmp_path / "apps/app").mkdir(parents=True)
    package = tmp_path / "packages/lib"
    (package / "lib").mkdir(parents=True)
    (tmp_path / "package.json").write_text(
        '{"workspaces":["apps/*","packages/*"]}', encoding="utf-8"
    )
    (package / "package.json").write_text(
        '{"name":"@demo/lib","main":"./lib"}', encoding="utf-8"
    )
    declaration = package / "lib/index.d.ts"
    declaration.touch()

    assert _resolve_workspace_import("@demo/lib", tmp_path / "apps/app") == declaration


def test_workspace_explicit_declaration_entry_keeps_base_target(tmp_path):
    (tmp_path / "apps/app").mkdir(parents=True)
    package = tmp_path / "packages/lib"
    (package / "lib").mkdir(parents=True)
    (package / "src").mkdir()
    (tmp_path / "package.json").write_text(
        '{"workspaces":["apps/*","packages/*"]}', encoding="utf-8"
    )
    (package / "package.json").write_text(
        '{"name":"@demo/lib","main":"./lib/index.d.ts"}', encoding="utf-8"
    )
    declaration = package / "lib/index.d.ts"
    source = package / "src/index.ts"
    declaration.touch()
    source.touch()

    assert _resolve_workspace_import("@demo/lib", tmp_path / "apps/app") == declaration


def test_cache_from_before_the_fix_is_not_reused(tmp_path, monkeypatch):
    import graphify.cache as cache
    from graphify.cache import load_cached, save_cached

    assert cache._AST_CACHE_SCHEMA >= 56
    importer = tmp_path / "src/entry.ts"
    importer.parent.mkdir()
    importer.write_text("import './api';\n")
    monkeypatch.setattr(cache, "_AST_CACHE_SCHEMA", 55)
    save_cached(importer, {"nodes": [], "edges": []}, root=tmp_path, kind="ast")
    monkeypatch.undo()

    assert load_cached(importer, root=tmp_path, kind="ast") is None
