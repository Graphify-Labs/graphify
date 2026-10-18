from pathlib import Path
from graphify.extract import extract


def graph_for(root, files):
    for name, text in files.items():
        (root / name).write_text(text)
    return extract([root / name for name in files], root=root, cache_root=root, parallel=False)


def test_star_cycle_with_real_definition_does_not_mask_unique_origin(tmp_path):
    g = graph_for(
        tmp_path,
        {
            "base.ts": "export const x=1;",
            "a.ts": 'export * from "./b.js"; export * from "./base.js";',
            "b.ts": 'export {x} from "./a.js";',
            "api.ts": 'export {x} from "./a.js";',
        },
    )
    edges = [
        e
        for e in g["edges"]
        if e["source"] == "api" and e["relation"] == "re_exports" and e["context"] == "re-export"
    ]
    assert {e["target"] for e in edges} == {"base_x"}


def test_sourceless_owned_node_is_not_an_export_definition(tmp_path):
    from graphify.extractors.resolution import _apply_symbol_resolution_facts
    from graphify.extractors.models import _SymbolResolutionFacts, _SymbolExportFact
    from graphify.extractors.base import _make_id, _file_stem

    base = tmp_path / "base.ts"
    api = tmp_path / "api.ts"
    nodes = [{"id": "orphan", "label": "x"}]
    edge = {
        "source": _make_id(str(api)),
        "target": _make_id(_file_stem(base), "x"),
        "relation": "re_exports",
        "context": "re-export",
        "source_file": str(api),
        "source_location": "L1",
        "target_file": str(base),
    }
    facts = _SymbolResolutionFacts()
    facts.exports.extend(
        [
            _SymbolExportFact(base, "x", 1, local_name="x"),
            _SymbolExportFact(api, "x", 1, target_path=base, target_name="x"),
        ]
    )
    _apply_symbol_resolution_facts([base, api], nodes, [edge], tmp_path, facts)
    assert edge["target"] != "orphan"
    assert edge["target_file"] == str(base)


def test_legacy_aggregate_pattern_facts_and_nodes_are_preserved(tmp_path):
    from graphify.extractors.resolution import (
        _parse_js_tree,
        _walk_js_tree,
        _js_exported_declaration_names,
    )

    for name, pattern, value in [("object", "{x}", "{x:1}"), ("array", "[x]", "[1]")]:
        root = tmp_path / name
        root.mkdir()
        g = graph_for(
            root,
            {
                "decl.ts": f"const holder={value}; export const {pattern}=holder;",
                "consumer.ts": 'import {x} from "./decl.js";',
            },
        )
        source, tree = _parse_js_tree(root / "decl.ts")
        assert [
            _js_exported_declaration_names(n, source)
            for n in _walk_js_tree(tree)
            if n.type == "export_statement"
        ] == [[pattern]]
        assert any(n["id"] == "decl_x" and n["label"] == pattern for n in g["nodes"])


def test_identifier_alias_fact_and_binding_are_preserved(tmp_path):
    from graphify.extractors.resolution import (
        _parse_js_tree,
        _walk_js_tree,
        _js_exported_declaration_names,
    )

    g = graph_for(
        tmp_path,
        {
            "decl.ts": "const original=1; export const alias=original;",
            "consumer.ts": 'import {alias} from "./decl.js";',
        },
    )
    source, tree = _parse_js_tree(tmp_path / "decl.ts")
    assert [
        _js_exported_declaration_names(n, source)
        for n in _walk_js_tree(tree)
        if n.type == "export_statement"
    ] == [["alias"]]
    assert any(
        e["source"] == "consumer" and e["target"] == "decl_alias" and e["relation"] == "imports"
        for e in g["edges"]
    )


def test_longer_export_cycle_with_definition_remains_resolvable(tmp_path):
    g = graph_for(
        tmp_path,
        {
            "base.ts": "export const x=1;",
            "a.ts": 'export * from "./b.js"; export * from "./base.js";',
            "b.ts": 'export {x} from "./c.js";',
            "c.ts": 'export {x} from "./a.js";',
            "api.ts": 'export {x} from "./a.js";',
        },
    )
    edges = [
        e
        for e in g["edges"]
        if e["source"] == "api" and e["relation"] == "re_exports" and e["context"] == "re-export"
    ]
    assert {e["target"] for e in edges} == {"base_x"}
