from graphify.extract import extract


def test_imported_then_exported_binding_has_owned_target(tmp_path):
    files = {
        "base.ts": "export const VALUE=1;",
        "bridge.ts": 'import {VALUE} from "./base.js"; export {VALUE};',
        "api.ts": 'export {VALUE} from "./bridge.js";',
    }
    paths = []
    for name, text in files.items():
        p = tmp_path / name
        p.write_text(text)
        paths.append(p)
    graph = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    ids = {n["id"] for n in graph["nodes"]}
    exports = [e for e in graph["edges"] if e["relation"] == "re_exports" and e["source"] == "api"]
    assert exports
    assert all(e["target"] in ids for e in exports), exports
    assert any(e["target"] == "base_value" for e in exports)


def graph_for(tmp_path, files):
    paths = []
    for name, text in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        paths.append(p)
    return extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)


def symbol_exports(graph, source):
    return [
        e
        for e in graph["edges"]
        if e["relation"] == "re_exports" and e["context"] == "re-export" and e["source"] == source
    ]


def test_renamed_import_and_export_keep_original_definition(tmp_path):
    g = graph_for(
        tmp_path,
        {
            "base.ts": "export const VALUE=1;",
            "bridge.ts": 'import {VALUE as local} from "./base.js"; export {local as publicValue};',
            "second.ts": 'export {publicValue as renamed} from "./bridge.js";',
            "api.ts": 'export {renamed as finalValue} from "./second.js";',
        },
    )
    assert {e["target"] for e in symbol_exports(g, "api")} == {"base_value"}
    assert {e["target"] for e in symbol_exports(g, "second")} == {"base_value"}


def test_same_line_exports_resolve_each_explicit_binding(tmp_path):
    g = graph_for(
        tmp_path,
        {
            "left.ts": "export const x=1;",
            "right.ts": "export const x=2;",
            "bridge.ts": 'import {x as a} from "./left.js"; import {x as b} from "./right.js"; export {a,b};',
            "api.ts": 'export {a,b} from "./bridge.js";',
        },
    )
    assert {e["target"] for e in symbol_exports(g, "api")} == {"left_x", "right_x"}


def test_imported_but_not_exported_name_stays_unresolved(tmp_path):
    g = graph_for(
        tmp_path,
        {
            "base.ts": "export const VALUE=1;",
            "bridge.ts": 'import {VALUE} from "./base.js"; export const other=2;',
            "api.ts": 'export {VALUE} from "./bridge.js";',
        },
    )
    assert {e["target"] for e in symbol_exports(g, "api")} == {"bridge_value"}


def test_existing_local_declaration_remains_owned(tmp_path):
    g = graph_for(
        tmp_path,
        {
            "base.ts": "export const VALUE=1;",
            "bridge.ts": 'import {VALUE as imported} from "./base.js"; export const VALUE=2;',
            "api.ts": 'export {VALUE} from "./bridge.js";',
        },
    )
    assert {e["target"] for e in symbol_exports(g, "api")} == {"bridge_value"}


def test_type_only_forwarding_preserves_edge_metadata(tmp_path):
    g = graph_for(
        tmp_path,
        {
            "base.ts": "export interface Shape {x:number;}",
            "bridge.ts": 'import type {Shape} from "./base.js"; export type {Shape};',
            "api.ts": 'export type {Shape} from "./bridge.js";',
        },
    )
    edges = symbol_exports(g, "api")
    assert {e["target"] for e in edges} == {"base_shape"}
    assert all(
        e.get("type_only") is True and e["source_file"] == "api.ts" and e["source_location"] == "L1"
        for e in edges
    )


def test_export_cycle_does_not_invent_definition(tmp_path):
    g = graph_for(
        tmp_path, {"a.ts": 'export {VALUE} from "./b.js";', "b.ts": 'export {VALUE} from "./a.js";'}
    )
    ids = {n["id"] for n in g["nodes"]}
    assert all(e["target"] not in ids for e in symbol_exports(g, "a") + symbol_exports(g, "b"))


def test_conflicting_named_exports_do_not_choose_last_definition(tmp_path):
    g = graph_for(
        tmp_path,
        {
            "left.ts": "export const x=1;",
            "right.ts": "export const x=2;",
            "bridge.ts": 'export {x} from "./left.js"; export {x} from "./right.js";',
            "api.ts": 'export {x} from "./bridge.js";',
        },
    )
    assert {e["target"] for e in symbol_exports(g, "bridge")} == {"left_x", "right_x"}
    assert {e["target"] for e in symbol_exports(g, "api")} == {"bridge_x"}


def test_conflicting_star_exports_do_not_choose_first_definition(tmp_path):
    g = graph_for(
        tmp_path,
        {
            "left.ts": "export const x=1;",
            "right.ts": "export const x=2;",
            "bridge.ts": 'export * from "./left.js"; export * from "./right.js";',
            "api.ts": 'export {x} from "./bridge.js";',
        },
    )
    assert {e["target"] for e in symbol_exports(g, "api")} == {"bridge_x"}


def test_unrepresented_explicit_star_export_blocks_false_unique_target(tmp_path):
    g = graph_for(
        tmp_path,
        {
            "left.ts": "export const x=1;",
            "right.ts": "const {x}=getValues(); export {x};",
            "bridge.ts": 'export * from "./left.js"; export * from "./right.js";',
            "api.ts": 'export {x} from "./bridge.js";',
        },
    )
    assert {e["target"] for e in symbol_exports(g, "api")} == {"bridge_x"}


def test_star_branch_without_export_does_not_block_unique_target(tmp_path):
    g = graph_for(
        tmp_path,
        {
            "left.ts": "export const x=1;",
            "right.ts": "export const other=2;",
            "bridge.ts": 'export * from "./left.js"; export * from "./right.js";',
            "api.ts": 'export {x} from "./bridge.js";',
        },
    )
    assert {e["target"] for e in symbol_exports(g, "api")} == {"left_x"}


def test_explicit_named_export_overrides_star_ambiguity(tmp_path):
    g = graph_for(
        tmp_path,
        {
            "left.ts": "export const x=1;",
            "right.ts": "export const x=2;",
            "bridge.ts": 'export * from "./left.js"; export * from "./right.js"; export {x} from "./left.js";',
            "api.ts": 'export {x} from "./bridge.js";',
        },
    )
    assert {e["target"] for e in symbol_exports(g, "api")} == {"left_x"}


def test_private_name_in_star_branch_is_not_an_export(tmp_path):
    g = graph_for(
        tmp_path,
        {
            "left.ts": "export const x=1;",
            "right.ts": "const x=2; export const other=3;",
            "bridge.ts": 'export * from "./left.js"; export * from "./right.js";',
            "api.ts": 'export {x} from "./bridge.js";',
        },
    )
    assert {e["target"] for e in symbol_exports(g, "api")} == {"left_x"}


def test_repointed_target_file_tracks_definition_and_preserves_source_site(tmp_path, monkeypatch):
    from pathlib import Path
    import graphify.extractors.resolution as resolution

    original = resolution._apply_symbol_resolution_facts
    observed = []

    def tracked(paths, nodes, edges, root, facts):
        def authored():
            return next(
                e
                for e in edges
                if e.get("relation") == "re_exports"
                and e.get("context") == "re-export"
                and Path(e["source_file"]).name == "api.ts"
            )

        before = dict(authored())
        original(paths, nodes, edges, root, facts)
        observed.append((before, dict(authored())))

    monkeypatch.setattr(resolution, "_apply_symbol_resolution_facts", tracked)
    graph_for(
        tmp_path,
        {
            "base.ts": "export const VALUE=1;",
            "bridge.ts": 'import {VALUE} from "./base.js"; export {VALUE};',
            "api.ts": 'export {VALUE} from "./bridge.js";',
        },
    )
    before, after = observed[0]
    assert Path(before["target_file"]).resolve() == (tmp_path / "bridge.ts").resolve()
    assert Path(after["target_file"]).resolve() == (tmp_path / "base.ts").resolve()
    assert {k: v for k, v in before.items() if k not in {"target", "target_file"}} == {
        k: v for k, v in after.items() if k not in {"target", "target_file"}
    }
