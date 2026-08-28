"""Tests for Rust ``use`` declaration resolution.

The extractor used to read a ``use`` declaration by string-splitting its text:
everything before the first ``{``, then the last ``::`` segment. That collapsed
a braced list to its shared prefix, glued an alias to its symbol
(``Entity as Risk``), and pointed every edge at a bare-name id no node ever
carried — so the edge dangled and was dropped at build time. A crate's prelude
therefore showed inbound edges and no outbound ones, orphaning every module it
re-exported.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract
from graphify.extractors.rust import (
    _resolve_rust_use_path,
    _rust_module_dirs,
    _rust_use_leaves,
)


def _leaves(body: str):
    from tree_sitter import Language, Parser

    import tree_sitter_rust as tsrust

    source = body.encode("utf-8")
    root = Parser(Language(tsrust.language())).parse(source).root_node
    out = []
    for decl in root.children:
        if decl.type != "use_declaration":
            continue
        out.extend(_rust_use_leaves(decl.child_by_field_name("argument"), source))
    return out


def _crate(tmp_path: Path) -> Path:
    """A crate laid out like a SeaORM-generated model tree."""
    (tmp_path / "src" / "models" / "_entities").mkdir(parents=True)
    (tmp_path / "Cargo.toml").write_text("[package]\nname = \"demo\"\n", encoding="utf-8")
    (tmp_path / "src" / "lib.rs").write_text("pub mod models;\n", encoding="utf-8")
    (tmp_path / "src" / "models" / "mod.rs").write_text(
        "pub mod _entities;\npub mod service;\n", encoding="utf-8"
    )
    (tmp_path / "src" / "models" / "_entities" / "mod.rs").write_text(
        "pub mod prelude;\npub mod risk;\n", encoding="utf-8"
    )
    (tmp_path / "src" / "models" / "_entities" / "risk.rs").write_text(
        "pub struct Entity;\nimpl Entity { pub fn find_risk() -> u32 { 1 } }\n",
        encoding="utf-8",
    )
    return tmp_path


def _graph(root: Path):
    result = extract(sorted(root.rglob("*.rs")), cache_root=root)
    nodes = {n["id"]: n for n in result["nodes"]}
    return result, nodes


def _edges(result, nodes, relation: str):
    return {
        (
            nodes.get(e["source"], {}).get("label"),
            nodes.get(e["target"], {}).get("label"),
        )
        for e in result["edges"]
        if e["relation"] == relation
    }


# ── use-tree parsing ──────────────────────────────────────────────────────────

def test_braced_list_yields_one_leaf_per_name():
    leaves = _leaves("use super::{a, b::C};\n")
    assert [(segs, alias) for segs, alias, _ in leaves] == [
        (("super", "a"), None),
        (("super", "b", "C"), None),
    ]


def test_nested_braces_and_alias_inside_a_list():
    leaves = _leaves("use crate::x::y::{z::{Deep}, other as O};\n")
    assert [(segs, alias) for segs, alias, _ in leaves] == [
        (("crate", "x", "y", "z", "Deep"), None),
        (("crate", "x", "y", "other"), "O"),
    ]


def test_as_clause_separates_symbol_from_alias():
    (segments, alias, wildcard), = _leaves("pub use super::risk::Entity as Risk;\n")
    assert segments == ("super", "risk", "Entity")
    assert alias == "Risk"
    assert wildcard is False


def test_wildcard_is_flagged_and_keeps_its_module_path():
    (segments, alias, wildcard), = _leaves("use crate::models::prelude::*;\n")
    assert segments == ("crate", "models", "prelude")
    assert alias is None
    assert wildcard is True


# ── module resolution ─────────────────────────────────────────────────────────

def test_module_dirs_for_mod_rs_and_for_a_plain_file(tmp_path):
    _crate(tmp_path)
    entities = tmp_path / "src" / "models" / "_entities"
    # `mod.rs` IS its module: children live beside it, `super` is one level up.
    self_dir, super_dir = _rust_module_dirs(entities / "mod.rs")
    assert self_dir == entities
    assert super_dir == entities.parent
    # A plain file's `super` is the directory holding it.
    self_dir, super_dir = _rust_module_dirs(entities / "risk.rs")
    assert super_dir == entities


def test_super_path_resolves_to_sibling_module_and_symbol(tmp_path):
    _crate(tmp_path)
    prelude = tmp_path / "src" / "models" / "_entities" / "prelude.rs"
    prelude.write_text("pub use super::risk::Entity;\n", encoding="utf-8")
    resolved = _resolve_rust_use_path(("super", "risk", "Entity"), prelude)
    assert resolved is not None
    module_file, symbol = resolved
    assert module_file == tmp_path / "src" / "models" / "_entities" / "risk.rs"
    assert symbol == "Entity"


def test_crate_path_resolves_from_the_crate_root(tmp_path):
    _crate(tmp_path)
    service = tmp_path / "src" / "models" / "service.rs"
    service.write_text("pub fn run() {}\n", encoding="utf-8")
    resolved = _resolve_rust_use_path(
        ("crate", "models", "_entities", "risk", "Entity"), service
    )
    assert resolved is not None
    module_file, symbol = resolved
    assert module_file == tmp_path / "src" / "models" / "_entities" / "risk.rs"
    assert symbol == "Entity"


def test_module_without_symbol_tail_resolves_to_the_module(tmp_path):
    _crate(tmp_path)
    service = tmp_path / "src" / "models" / "service.rs"
    service.write_text("pub fn run() {}\n", encoding="utf-8")
    resolved = _resolve_rust_use_path(("crate", "models", "_entities", "risk"), service)
    assert resolved is not None
    module_file, symbol = resolved
    assert module_file.name == "risk.rs"
    assert symbol is None


def test_external_crate_does_not_resolve(tmp_path):
    _crate(tmp_path)
    service = tmp_path / "src" / "models" / "service.rs"
    service.write_text("pub fn run() {}\n", encoding="utf-8")
    assert _resolve_rust_use_path(("std", "collections", "HashMap"), service) is None


# ── emitted edges ─────────────────────────────────────────────────────────────

def test_no_use_edge_points_at_a_phantom_node(tmp_path):
    """Regression: the old id scheme produced targets no node carried, so the
    edges were silently dropped and the module looked like a dead end."""
    _crate(tmp_path)
    (tmp_path / "src" / "models" / "_entities" / "prelude.rs").write_text(
        "pub use super::risk::Entity as Risk;\n", encoding="utf-8"
    )
    (tmp_path / "src" / "models" / "service.rs").write_text(
        "use std::collections::HashMap;\n"
        "use crate::models::_entities::{prelude, risk};\n"
        "pub fn run() -> u32 { 1 }\n",
        encoding="utf-8",
    )
    result, nodes = _graph(tmp_path)
    dangling = [
        e for e in result["edges"]
        if e["target"] not in nodes and e["relation"] in ("imports_from", "imports")
    ]
    assert dangling == []


def test_prelude_gains_outbound_edges_to_what_it_reexports(tmp_path):
    """The symptom that started this: 466 inbound edges, 0 outbound."""
    _crate(tmp_path)
    prelude = tmp_path / "src" / "models" / "_entities" / "prelude.rs"
    prelude.write_text("pub use super::risk::Entity as Risk;\n", encoding="utf-8")
    result, nodes = _graph(tmp_path)
    # Look the node up by label: the corpus pass canonicalizes absolute-path
    # prefixes out of ids, so the extraction-time id is not the final one.
    prelude_nid = next(
        nid for nid, n in nodes.items()
        if n.get("label") == "prelude.rs" and str(n.get("source_file", "")).endswith("prelude.rs")
    )
    outbound = [e for e in result["edges"] if e["source"] == prelude_nid]
    assert outbound, "prelude re-exports a module but has no outbound edge"
    assert ("prelude.rs", "risk.rs") in _edges(result, nodes, "imports_from")


def test_pub_use_is_a_reexport_and_lands_on_the_defining_symbol(tmp_path):
    _crate(tmp_path)
    (tmp_path / "src" / "models" / "_entities" / "prelude.rs").write_text(
        "pub use super::risk::Entity as Risk;\n", encoding="utf-8"
    )
    result, nodes = _graph(tmp_path)
    assert ("prelude.rs", "Entity") in _edges(result, nodes, "re_exports")


def test_plain_use_is_an_import_not_a_reexport(tmp_path):
    _crate(tmp_path)
    (tmp_path / "src" / "models" / "service.rs").write_text(
        "use crate::models::_entities::risk::Entity;\n"
        "pub fn run() -> u32 { Entity::find_risk() }\n",
        encoding="utf-8",
    )
    result, nodes = _graph(tmp_path)
    assert ("service.rs", "Entity") in _edges(result, nodes, "imports")
    assert not any(
        src == "service.rs" for src, _ in _edges(result, nodes, "re_exports")
    )


def test_consumer_resolves_through_the_barrel_to_the_definition(tmp_path):
    """A consumer importing through a prelude reaches the defining symbol, the
    same way a JS barrel re-export resolves."""
    _crate(tmp_path)
    (tmp_path / "src" / "models" / "_entities" / "prelude.rs").write_text(
        "pub use super::risk::Entity;\n", encoding="utf-8"
    )
    (tmp_path / "src" / "models" / "service.rs").write_text(
        "use crate::models::_entities::prelude::Entity;\n"
        "pub fn run() -> u32 { Entity::find_risk() }\n",
        encoding="utf-8",
    )
    result, nodes = _graph(tmp_path)
    imports = _edges(result, nodes, "imports")
    assert ("service.rs", "Entity") in imports
    # And the file-level hop through the barrel is kept, not collapsed away.
    assert ("service.rs", "prelude.rs") in _edges(result, nodes, "imports_from")


def test_braced_import_edges_reach_every_named_module(tmp_path):
    """The old prefix-splitting emitted ONE edge naming the shared prefix."""
    _crate(tmp_path)
    (tmp_path / "src" / "models" / "_entities" / "prelude.rs").write_text(
        "pub use super::risk::Entity;\n", encoding="utf-8"
    )
    (tmp_path / "src" / "models" / "service.rs").write_text(
        "use crate::models::_entities::{prelude, risk};\n"
        "pub fn run() -> u32 { 1 }\n",
        encoding="utf-8",
    )
    result, nodes = _graph(tmp_path)
    imports_from = _edges(result, nodes, "imports_from")
    assert ("service.rs", "prelude.rs") in imports_from
    assert ("service.rs", "risk.rs") in imports_from


def test_glob_reexport_edges_the_module_but_names_no_symbol(tmp_path):
    _crate(tmp_path)
    (tmp_path / "src" / "models" / "_entities" / "prelude.rs").write_text(
        "pub use super::risk::*;\n", encoding="utf-8"
    )
    result, nodes = _graph(tmp_path)
    assert ("prelude.rs", "risk.rs") in _edges(result, nodes, "imports_from")
    # A glob publishes an unknown set of names, so no single symbol is claimed.
    assert not _edges(result, nodes, "re_exports")


def test_external_crate_import_still_edges_a_named_stub(tmp_path):
    """`use std::collections::HashMap` cannot resolve on disk, but must still
    produce a real endpoint rather than a dropped edge."""
    _crate(tmp_path)
    (tmp_path / "src" / "models" / "service.rs").write_text(
        "use std::collections::HashMap;\npub fn run() -> u32 { 1 }\n",
        encoding="utf-8",
    )
    result, nodes = _graph(tmp_path)
    assert ("service.rs", "HashMap") in _edges(result, nodes, "imports_from")
