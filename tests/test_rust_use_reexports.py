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

import os

import pytest
from pathlib import Path

from graphify.extract import extract
from graphify.extractors.rust import (
    _resolve_rust_use_path,
    extract_rust,
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


def test_pub_self_use_is_not_a_reexport(tmp_path):
    """`pub(self)` restricts to the current module — as private as a bare `use`."""
    _crate(tmp_path)
    (tmp_path / "src" / "models" / "_entities" / "prelude.rs").write_text(
        "pub(self) use super::risk::Entity;\n", encoding="utf-8"
    )
    result, nodes = _graph(tmp_path)
    assert ("prelude.rs", "Entity") in _edges(result, nodes, "imports")
    assert ("prelude.rs", "Entity") not in _edges(result, nodes, "re_exports")


def test_pub_crate_use_is_still_a_reexport(tmp_path):
    """`pub(crate)` republishes within the crate, so consumers can follow it."""
    _crate(tmp_path)
    (tmp_path / "src" / "models" / "_entities" / "prelude.rs").write_text(
        "pub(crate) use super::risk::Entity;\n", encoding="utf-8"
    )
    result, nodes = _graph(tmp_path)
    assert ("prelude.rs", "Entity") in _edges(result, nodes, "re_exports")


def test_use_list_self_names_the_module_not_a_symbol():
    """`use foo::bar::{self, Baz}` binds `foo::bar`, not a symbol called `self`."""
    leaves = _leaves("use crate::models::risk::{self, Entity};\n")
    segments = {leaf[0] for leaf in leaves}
    assert ("crate", "models", "risk") in segments
    assert ("crate", "models", "risk", "self") not in segments
    assert ("crate", "models", "risk", "Entity") in segments


def test_use_list_self_edges_the_module_file(tmp_path):
    _crate(tmp_path)
    (tmp_path / "src" / "models" / "service.rs").write_text(
        "use crate::models::_entities::risk::{self, Entity};\n"
        "pub fn run() -> u32 { 1 }\n",
        encoding="utf-8",
    )
    result, nodes = _graph(tmp_path)
    assert ("service.rs", "risk.rs") in _edges(result, nodes, "imports_from")
    # No node is minted for a symbol named `self`.
    assert "self" not in {n.get("label") for n in result["nodes"]}


def test_leading_self_path_resolves_a_child_of_a_mod_rs(tmp_path):
    """`self::x` in `_entities/mod.rs` names its child `_entities::risk`."""
    _crate(tmp_path)
    (tmp_path / "src" / "models" / "_entities" / "mod.rs").write_text(
        "pub mod prelude;\npub mod risk;\nuse self::risk::Entity;\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "models" / "_entities" / "prelude.rs").write_text(
        "pub use super::risk::Entity;\n", encoding="utf-8"
    )
    result, nodes = _graph(tmp_path)
    assert ("mod.rs", "risk.rs") in _edges(result, nodes, "imports_from")


def test_leading_self_path_does_not_reach_a_sibling_module(tmp_path):
    """`self::risk` inside `_entities/prelude.rs` is `_entities::prelude::risk`.

    `prelude.rs` has no sibling `prelude/` directory, so it declares no child
    modules and the path resolves to nothing. Falling back to the containing
    directory would make `self::` behave like `super::` and wrongly edge the
    sibling `_entities/risk.rs`.
    """
    _crate(tmp_path)
    (tmp_path / "src" / "models" / "_entities" / "prelude.rs").write_text(
        "use self::risk::Entity;\n", encoding="utf-8"
    )
    result, nodes = _graph(tmp_path)
    assert ("prelude.rs", "risk.rs") not in _edges(result, nodes, "imports_from")


def test_self_path_reaches_a_child_in_a_sibling_directory(tmp_path):
    """A plain `foo.rs` WITH a sibling `foo/` does have children."""
    _crate(tmp_path)
    (tmp_path / "src" / "models" / "service").mkdir(parents=True)
    (tmp_path / "src" / "models" / "service" / "helper.rs").write_text(
        "pub struct Helper;\n", encoding="utf-8"
    )
    (tmp_path / "src" / "models" / "service.rs").write_text(
        "pub mod helper;\nuse self::helper::Helper;\npub fn run() -> u32 { 1 }\n",
        encoding="utf-8",
    )
    result, nodes = _graph(tmp_path)
    assert ("service.rs", "helper.rs") in _edges(result, nodes, "imports_from")


def test_super_walk_stops_at_the_crate_root(tmp_path):
    """`super::super::…` past the crate root must resolve to nothing.

    Unclamped, the walk leaves `src/` and can resolve an unrelated file higher
    up the filesystem — `models.rs` next to `Cargo.toml`, say.
    """
    _crate(tmp_path)
    (tmp_path / "models.rs").write_text("pub struct Outside;\n", encoding="utf-8")
    (tmp_path / "src" / "models" / "service.rs").write_text(
        "use super::super::super::models::Outside;\npub fn run() -> u32 { 1 }\n",
        encoding="utf-8",
    )
    result, nodes = _graph(tmp_path)
    imports_from = _edges(result, nodes, "imports_from")
    assert ("service.rs", "models.rs") not in imports_from
    # It falls back to a sourceless stub so the edge still has an endpoint.
    assert ("service.rs", "Outside") in imports_from


def test_super_still_resolves_within_the_crate(tmp_path):
    _crate(tmp_path)
    (tmp_path / "src" / "models" / "_entities" / "prelude.rs").write_text(
        "use super::super::service::run;\n", encoding="utf-8"
    )
    (tmp_path / "src" / "models" / "service.rs").write_text(
        "pub fn run() -> u32 { 1 }\n", encoding="utf-8"
    )
    result, nodes = _graph(tmp_path)
    assert ("prelude.rs", "service.rs") in _edges(result, nodes, "imports_from")


def test_multi_segment_symbol_tail_attributes_the_item(tmp_path):
    """`use crate::…::Status::Active` names the enum the module defines.

    Requiring a SINGLE trailing segment dropped the whole edge, so an enum
    variant import contributed nothing.
    """
    _crate(tmp_path)
    (tmp_path / "src" / "models" / "_entities" / "risk.rs").write_text(
        "pub enum Status { Active }\npub struct Entity;\n", encoding="utf-8"
    )
    (tmp_path / "src" / "models" / "service.rs").write_text(
        "use crate::models::_entities::risk::Status::Active;\n"
        "pub fn run() -> u32 { 1 }\n",
        encoding="utf-8",
    )
    result, nodes = _graph(tmp_path)
    assert ("service.rs", "risk.rs") in _edges(result, nodes, "imports_from")
    assert ("service.rs", "Status") in _edges(result, nodes, "imports")


def test_external_pub_use_keeps_the_reexport_relation(tmp_path):
    """`pub use anyhow::Result;` republishes an external name.

    Without the symbol-level `re_exports` the barrel collapse cannot follow a
    consumer through the module, which is the point of resolving preludes.
    """
    _crate(tmp_path)
    (tmp_path / "src" / "models" / "_entities" / "prelude.rs").write_text(
        "pub use anyhow::Result;\n", encoding="utf-8"
    )
    result, nodes = _graph(tmp_path)
    assert ("prelude.rs", "Result") in _edges(result, nodes, "re_exports")
    assert ("prelude.rs", "Result") in _edges(result, nodes, "imports_from")


def test_external_plain_use_is_not_a_reexport(tmp_path):
    _crate(tmp_path)
    (tmp_path / "src" / "models" / "service.rs").write_text(
        "use anyhow::Result;\npub fn run() -> u32 { 1 }\n", encoding="utf-8"
    )
    result, nodes = _graph(tmp_path)
    assert ("service.rs", "Result") in _edges(result, nodes, "imports_from")
    assert not _edges(result, nodes, "re_exports")


def test_symbol_defined_in_the_anchor_module_itself_resolves(tmp_path):
    """`use crate::Config` names an item of `lib.rs`, not of a child module.

    Requiring at least one module segment to resolve first dropped the edge.
    """
    _crate(tmp_path)
    (tmp_path / "src" / "lib.rs").write_text(
        "pub mod models;\npub struct Config;\n", encoding="utf-8"
    )
    (tmp_path / "src" / "models" / "service.rs").write_text(
        "use crate::Config;\npub fn run() -> u32 { 1 }\n", encoding="utf-8"
    )
    result, nodes = _graph(tmp_path)
    assert ("service.rs", "lib.rs") in _edges(result, nodes, "imports_from")
    assert ("service.rs", "Config") in _edges(result, nodes, "imports")


def test_self_prefixed_own_item_resolves_without_a_child_directory(tmp_path):
    """`use self::Config;` in a childless `foo.rs` names that file's own item."""
    _crate(tmp_path)
    (tmp_path / "src" / "models" / "service.rs").write_text(
        "use self::Config;\npub struct Config;\npub fn run() -> u32 { 1 }\n",
        encoding="utf-8",
    )
    result, nodes = _graph(tmp_path)
    assert ("service.rs", "Config") in _edges(result, nodes, "imports")


def test_external_crate_does_not_resolve_to_the_crate_root_file(tmp_path):
    """A bare path is a GUESS at being crate-relative.

    Seeding the anchor's own file for that guess would make every external
    crate resolve to a symbol named after it inside `lib.rs`.
    """
    _crate(tmp_path)
    (tmp_path / "src" / "models" / "service.rs").write_text(
        "use anyhow::Result;\npub fn run() -> u32 { 1 }\n", encoding="utf-8"
    )
    result, nodes = _graph(tmp_path)
    imports_from = _edges(result, nodes, "imports_from")
    assert ("service.rs", "lib.rs") not in imports_from
    assert ("service.rs", "Result") in imports_from


def test_aliased_self_in_a_use_list_names_the_module():
    """`use foo::bar::{self as bar_mod, Baz}` aliases the module `foo::bar`."""
    leaves = _leaves("use crate::models::risk::{self as risk_mod, Entity};\n")
    by_alias = {leaf[1]: leaf[0] for leaf in leaves}
    assert by_alias["risk_mod"] == ("crate", "models", "risk")
    assert ("crate", "models", "risk", "self") not in {leaf[0] for leaf in leaves}


def test_aliased_self_edges_the_module_file(tmp_path):
    _crate(tmp_path)
    (tmp_path / "src" / "models" / "service.rs").write_text(
        "use crate::models::_entities::risk::{self as risk_mod, Entity};\n"
        "pub fn run() -> u32 { 1 }\n",
        encoding="utf-8",
    )
    result, nodes = _graph(tmp_path)
    assert ("service.rs", "risk.rs") in _edges(result, nodes, "imports_from")
    assert "self" not in {n.get("label") for n in result["nodes"]}


def test_named_bin_resolves_crate_against_its_own_module_tree(tmp_path):
    """`src/bin/tool.rs` is its own crate root.

    `crate::helper` there means `src/bin/tool/helper.rs`, not the library's
    `src/helper.rs` — resolving it against `src/` edges the wrong file.
    """
    _crate(tmp_path)
    (tmp_path / "src" / "helper.rs").write_text(
        "pub struct Wrong;\n", encoding="utf-8"
    )
    (tmp_path / "src" / "bin" / "tool").mkdir(parents=True)
    (tmp_path / "src" / "bin" / "tool" / "helper.rs").write_text(
        "pub struct Helper;\n", encoding="utf-8"
    )
    (tmp_path / "src" / "bin" / "tool.rs").write_text(
        "mod helper;\nuse crate::helper::Helper;\nfn main() {}\n", encoding="utf-8"
    )
    result, nodes = _graph(tmp_path)
    imports_from = _edges(result, nodes, "imports_from")
    assert ("tool.rs", "helper.rs") in imports_from
    helper_targets = {
        nodes[e["target"]]["source_file"]
        for e in result["edges"]
        if nodes.get(e["source"], {}).get("label") == "tool.rs"
        and e["relation"] == "imports_from"
        and nodes.get(e["target"], {}).get("label") == "helper.rs"
    }
    assert helper_targets == {"src/bin/tool/helper.rs"}


def test_example_crate_root_does_not_reach_the_library_src(tmp_path):
    """`examples/demo.rs` is its own crate too, and sits beside `src/`."""
    _crate(tmp_path)
    (tmp_path / "src" / "helper.rs").write_text(
        "pub struct Wrong;\n", encoding="utf-8"
    )
    (tmp_path / "examples").mkdir()
    (tmp_path / "examples" / "demo.rs").write_text(
        "use crate::helper::Wrong;\nfn main() {}\n", encoding="utf-8"
    )
    result, nodes = _graph(tmp_path)
    assert ("demo.rs", "helper.rs") not in _edges(result, nodes, "imports_from")


def test_library_module_still_resolves_crate_against_src(tmp_path):
    """The bin/example carve-out must not disturb an ordinary library module."""
    _crate(tmp_path)
    (tmp_path / "src" / "models" / "service.rs").write_text(
        "use crate::models::_entities::risk::Entity;\npub fn run() -> u32 { 1 }\n",
        encoding="utf-8",
    )
    result, nodes = _graph(tmp_path)
    assert ("service.rs", "risk.rs") in _edges(result, nodes, "imports_from")


def test_bin_directory_form_is_unaffected(tmp_path):
    """`src/bin/tool/main.rs` IS its module, so `src` plus the walk suffices."""
    _crate(tmp_path)
    (tmp_path / "src" / "bin" / "tool").mkdir(parents=True)
    (tmp_path / "src" / "bin" / "tool" / "helper.rs").write_text(
        "pub struct Helper;\n", encoding="utf-8"
    )
    (tmp_path / "src" / "bin" / "tool" / "main.rs").write_text(
        "mod helper;\nuse self::helper::Helper;\nfn main() {}\n", encoding="utf-8"
    )
    result, nodes = _graph(tmp_path)
    assert ("main.rs", "helper.rs") in _edges(result, nodes, "imports_from")


def test_super_walk_without_a_cargo_toml_resolves_nothing(tmp_path):
    """No `Cargo.toml` above the file means no root to clamp against.

    The clamp was skipped entirely when `_rust_crate_src_root` returned None,
    so the walk climbed the filesystem unbounded.
    """
    (tmp_path / "models.rs").write_text("pub struct Outside;\n", encoding="utf-8")
    loose = tmp_path / "a" / "b" / "c"
    loose.mkdir(parents=True)
    (loose / "service.rs").write_text(
        "use super::super::super::models::Outside;\npub fn run() -> u32 { 1 }\n",
        encoding="utf-8",
    )
    result, nodes = _graph(tmp_path)
    imports_from = _edges(result, nodes, "imports_from")
    assert ("service.rs", "models.rs") not in imports_from
    assert ("service.rs", "Outside") in imports_from


def _use_edges(path: Path):
    """Edges straight from the extractor.

    `local_alias` is a transient import-resolution hint that `extract()` pops
    once the language resolvers have run (see the note beside the `pop` in
    extract.py), so the alias has to be asserted at this layer.
    """
    return [
        e for e in extract_rust(path)["edges"]
        if e["relation"] in ("imports", "imports_from", "re_exports")
    ]


def test_resolved_symbol_alias_is_recorded_on_the_edge(tmp_path):
    """`use …::Entity as Risk;` — the alias was parsed and then dropped.

    `local_alias` is the field the corpus-level receiver resolution already
    reads (#2082), so recording it there is what lets an aliased receiver
    match the import edge it came from.
    """
    _crate(tmp_path)
    service = tmp_path / "src" / "models" / "service.rs"
    service.write_text(
        "use crate::models::_entities::risk::Entity as Risk;\n"
        "pub fn run() -> u32 { 1 }\n",
        encoding="utf-8",
    )
    aliased = [e for e in _use_edges(service) if e.get("local_alias") == "Risk"]
    assert len(aliased) == 1
    assert aliased[0]["relation"] == "imports"
    assert aliased[0]["target_file"].endswith("risk.rs")


def test_module_alias_is_recorded_on_the_file_edge(tmp_path):
    """`use crate::…::risk as risk_model;` aliases the MODULE, not a symbol."""
    _crate(tmp_path)
    service = tmp_path / "src" / "models" / "service.rs"
    service.write_text(
        "use crate::models::_entities::risk as risk_model;\n"
        "pub fn run() -> u32 { 1 }\n",
        encoding="utf-8",
    )
    aliased = [e for e in _use_edges(service) if e.get("local_alias") == "risk_model"]
    assert len(aliased) == 1
    assert aliased[0]["relation"] == "imports_from"
    assert aliased[0]["target_file"].endswith("risk.rs")


def test_unresolved_alias_still_names_the_local_binding(tmp_path):
    """`use anyhow::Result as AnyResult;` stubs under the ALIAS, not `Result`."""
    _crate(tmp_path)
    service = tmp_path / "src" / "models" / "service.rs"
    service.write_text(
        "use anyhow::Result as AnyResult;\npub fn run() -> u32 { 1 }\n",
        encoding="utf-8",
    )
    labels = {n["label"] for n in extract_rust(service)["nodes"]}
    assert "AnyResult" in labels
    assert "Result" not in labels


def test_unaliased_import_records_no_alias(tmp_path):
    _crate(tmp_path)
    service = tmp_path / "src" / "models" / "service.rs"
    service.write_text(
        "use crate::models::_entities::risk::Entity;\npub fn run() -> u32 { 1 }\n",
        encoding="utf-8",
    )
    assert not [e for e in _use_edges(service) if e.get("local_alias")]


def test_module_under_a_named_bin_anchors_crate_at_that_bin(tmp_path):
    """`crate::` inside `src/bin/tool/helper.rs` is the bin crate, not `src`."""
    _crate(tmp_path)
    (tmp_path / "src" / "shared.rs").write_text("pub struct Wrong;\n", encoding="utf-8")
    (tmp_path / "src" / "bin" / "tool").mkdir(parents=True)
    (tmp_path / "src" / "bin" / "tool" / "shared.rs").write_text(
        "pub struct Shared;\n", encoding="utf-8"
    )
    (tmp_path / "src" / "bin" / "tool" / "helper.rs").write_text(
        "use crate::shared::Shared;\npub fn go() -> u32 { 1 }\n", encoding="utf-8"
    )
    (tmp_path / "src" / "bin" / "tool.rs").write_text(
        "mod helper;\nmod shared;\nfn main() {}\n", encoding="utf-8"
    )
    result, nodes = _graph(tmp_path)
    targets = {
        nodes[e["target"]]["source_file"]
        for e in result["edges"]
        if nodes.get(e["source"], {}).get("label") == "helper.rs"
        and e["relation"] == "imports_from"
        and nodes.get(e["target"], {}).get("label") == "shared.rs"
    }
    assert targets == {"src/bin/tool/shared.rs"}


def test_super_still_resolves_inside_a_named_bin_crate(tmp_path):
    """The clamp must accept a bin crate's own root as the floor."""
    _crate(tmp_path)
    (tmp_path / "src" / "bin" / "tool" / "deep").mkdir(parents=True)
    (tmp_path / "src" / "bin" / "tool" / "shared.rs").write_text(
        "pub struct Shared;\n", encoding="utf-8"
    )
    (tmp_path / "src" / "bin" / "tool" / "deep" / "mod.rs").write_text(
        "use super::shared::Shared;\npub fn go() -> u32 { 1 }\n", encoding="utf-8"
    )
    (tmp_path / "src" / "bin" / "tool.rs").write_text(
        "mod deep;\nmod shared;\nfn main() {}\n", encoding="utf-8"
    )
    result, nodes = _graph(tmp_path)
    assert ("mod.rs", "shared.rs") in _edges(result, nodes, "imports_from")


def test_main_rs_prefers_its_own_crate_root_over_lib_rs(tmp_path):
    """A package with both roots in `src/` must not attribute main's item to lib."""
    _crate(tmp_path)
    (tmp_path / "src" / "lib.rs").write_text(
        "pub mod models;\npub struct Config;\n", encoding="utf-8"
    )
    (tmp_path / "src" / "main.rs").write_text(
        "use crate::Config;\npub struct Config;\nfn main() {}\n", encoding="utf-8"
    )
    result, nodes = _graph(tmp_path)
    targets = {
        nodes[e["target"]]["source_file"]
        for e in result["edges"]
        if nodes.get(e["source"], {}).get("label") == "main.rs"
        and e["relation"] == "imports"
        and nodes.get(e["target"], {}).get("label") == "Config"
    }
    assert targets == {"src/main.rs"}


def test_self_prefixed_multi_segment_path_attributes_the_item(tmp_path):
    """`use self::Status::Active;` names this module's own enum.

    Requiring exactly two segments dropped the edge for anything deeper.
    """
    _crate(tmp_path)
    service = tmp_path / "src" / "models" / "service.rs"
    service.write_text(
        "use self::Status::Active;\npub enum Status { Active }\n"
        "pub fn run() -> u32 { 1 }\n",
        encoding="utf-8",
    )
    result, nodes = _graph(tmp_path)
    assert ("service.rs", "Status") in _edges(result, nodes, "imports")


def test_mod_rs_module_alias_compares_against_the_written_name(tmp_path):
    """A `mod.rs` file's stem is `mod`, not the module it defines.

    Comparing the alias against the stem stamped a redundant alias
    (`as _entities`) as though it renamed something.
    """
    _crate(tmp_path)
    service = tmp_path / "src" / "models" / "service.rs"
    service.write_text(
        "use crate::models::_entities as _entities;\npub fn run() -> u32 { 1 }\n",
        encoding="utf-8",
    )
    assert not [e for e in _use_edges(service) if e.get("local_alias")]


def test_mod_rs_module_alias_is_still_recorded_when_it_renames(tmp_path):
    _crate(tmp_path)
    service = tmp_path / "src" / "models" / "service.rs"
    service.write_text(
        "use crate::models::_entities as ents;\npub fn run() -> u32 { 1 }\n",
        encoding="utf-8",
    )
    aliased = [e for e in _use_edges(service) if e.get("local_alias") == "ents"]
    assert len(aliased) == 1
    assert aliased[0]["target_file"].endswith("_entities/mod.rs")


# ── Exhaustive resolver sweep ─────────────────────────────────────────────────
# Four review rounds running found successively narrower edge cases in
# _resolve_rust_use_path, each one in a layout or path shape the previous fix
# had not considered. This matrix enumerates the input space instead: every
# crate layout Cargo supports on disk, crossed with every anchor keyword and
# path depth. It pins two invariants over the whole product — a resolved path
# never escapes the crate, and a resolved symbol is never a module name — plus
# the per-case answers, so a regression names itself.

_SWEEP_LAYOUTS: dict[str, list[str]] = {
    "lib": [
        "src/lib.rs", "src/shared.rs",
        "src/models/mod.rs", "src/models/risk.rs",
    ],
    "lib_and_main": ["src/lib.rs", "src/main.rs", "src/shared.rs"],
    "no_src": ["lib.rs", "shared.rs", "sub/mod.rs"],
    "src_bin": [
        "src/lib.rs", "src/shared.rs",
        "src/bin/tool.rs", "src/bin/tool/helper.rs", "src/bin/tool/shared.rs",
    ],
    "top_level_bin": ["src/lib.rs", "src/shared.rs", "bin/tool.rs"],
    "examples": [
        "src/lib.rs", "src/shared.rs",
        "examples/demo.rs", "examples/demo/helper.rs",
    ],
}

_SWEEP_PATHS: tuple[tuple[str, ...], ...] = (
    ("crate", "X"),
    ("crate", "shared", "X"),
    ("crate", "models", "risk", "X"),
    ("crate", "models", "risk", "Status", "Active"),
    ("self", "X"),
    ("self", "X", "Y"),
    ("self", "helper", "X"),
    ("super", "shared", "X"),
    ("super", "super", "shared", "X"),
    ("super", "super", "super", "super", "outside", "X"),
    ("shared", "X"),
    ("anyhow", "Result"),
)


def _sweep_crate(tmp_path: Path, files: list[str]) -> Path:
    """Lay the crate out under `pkg/`, with bait namesakes above it.

    The bait must sit OUTSIDE the package: a package with no `src/` treats its
    own root as the source root, so bait placed there would be legitimately
    in-crate and the escape check would be vacuous.
    """
    root = tmp_path / "pkg"
    root.mkdir()
    (root / "Cargo.toml").write_text('[package]\nname = "d"\n', encoding="utf-8")
    for bait in ("outside.rs", "shared.rs", "lib.rs"):
        (tmp_path / bait).write_text("pub struct X;\n", encoding="utf-8")
    for rel in files:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("pub struct X;\n", encoding="utf-8")
    return root


def _sweep(tmp_path: Path, layout: str) -> dict[tuple[str, str], tuple[str, str | None]]:
    """Every (origin file, use path) that resolves, as repo-relative answers."""
    root = _sweep_crate(tmp_path, _SWEEP_LAYOUTS[layout])
    out: dict[tuple[str, str], tuple[str, str | None]] = {}
    for origin in _SWEEP_LAYOUTS[layout]:
        for segments in _SWEEP_PATHS:
            resolved = _resolve_rust_use_path(segments, root / origin)
            if resolved is None:
                continue
            module_file, symbol = resolved
            # Relative to the crate root, so an escape shows up as `../…`.
            rel = os.path.relpath(module_file, root)
            out[(origin, "::".join(segments))] = (rel, symbol)
    return out


@pytest.mark.parametrize("layout", sorted(_SWEEP_LAYOUTS))
def test_sweep_never_escapes_the_crate(tmp_path, layout):
    """No resolution may land outside the crate's own source tree.

    `outside.rs` and a top-level `shared.rs` sit beside the crate as bait for
    a `super::` walk or a crate-relative guess that climbs too far.
    """
    for (origin, path_text), (target, _symbol) in _sweep(tmp_path, layout).items():
        assert not target.startswith(".."), (
            f"{layout}: {origin} {path_text} escaped to {target}"
        )


@pytest.mark.parametrize("layout", sorted(_SWEEP_LAYOUTS))
def test_sweep_never_attributes_a_module_name_as_a_symbol(tmp_path, layout):
    """A `crate::`-anchored path must not attribute a module name as a symbol.

    `crate::models::risk::X` in a layout with no `models/` used to resolve to
    `(lib.rs, "models")` — a symbol nothing defines. Restricted to `crate::`
    because a CHILDLESS module may legitimately define an item that shares a
    name with one of its siblings, so `self::helper::X` resolving to
    `(helper.rs, "helper")` is a real answer, not a leaked module name.
    """
    module_names = {Path(f).stem for f in _SWEEP_LAYOUTS[layout]} - {"mod", "lib", "main"}
    for (origin, path_text), (target, symbol) in _sweep(tmp_path, layout).items():
        if not path_text.startswith("crate::"):
            continue
        assert symbol not in module_names, (
            f"{layout}: {origin} {path_text} -> {target} sym={symbol}"
        )


@pytest.mark.parametrize("layout", sorted(_SWEEP_LAYOUTS))
def test_sweep_external_crate_never_resolves(tmp_path, layout):
    """`use anyhow::Result` has no on-disk answer in any layout."""
    resolved = _sweep(tmp_path, layout)
    assert not [k for k in resolved if k[1] == "anyhow::Result"]


def test_sweep_answers_are_pinned(tmp_path):
    """The exact resolutions for the library layout, so a change is visible."""
    assert _sweep(tmp_path, "lib") == {
        ('src/lib.rs', 'crate::X'): ('src/lib.rs', 'X'),
        ('src/lib.rs', 'crate::models::risk::Status::Active'): ('src/models/risk.rs', 'Status'),
        ('src/lib.rs', 'crate::models::risk::X'): ('src/models/risk.rs', 'X'),
        ('src/lib.rs', 'crate::shared::X'): ('src/shared.rs', 'X'),
        ('src/lib.rs', 'self::X'): ('src/lib.rs', 'X'),
        ('src/lib.rs', 'shared::X'): ('src/shared.rs', 'X'),
        ('src/models/mod.rs', 'crate::X'): ('src/lib.rs', 'X'),
        ('src/models/mod.rs', 'crate::models::risk::Status::Active'): ('src/models/risk.rs', 'Status'),
        ('src/models/mod.rs', 'crate::models::risk::X'): ('src/models/risk.rs', 'X'),
        ('src/models/mod.rs', 'crate::shared::X'): ('src/shared.rs', 'X'),
        ('src/models/mod.rs', 'self::X'): ('src/models/mod.rs', 'X'),
        ('src/models/mod.rs', 'shared::X'): ('src/shared.rs', 'X'),
        ('src/models/mod.rs', 'super::shared::X'): ('src/shared.rs', 'X'),
        ('src/models/risk.rs', 'crate::X'): ('src/lib.rs', 'X'),
        ('src/models/risk.rs', 'crate::models::risk::Status::Active'): ('src/models/risk.rs', 'Status'),
        ('src/models/risk.rs', 'crate::models::risk::X'): ('src/models/risk.rs', 'X'),
        ('src/models/risk.rs', 'crate::shared::X'): ('src/shared.rs', 'X'),
        ('src/models/risk.rs', 'self::X'): ('src/models/risk.rs', 'X'),
        ('src/models/risk.rs', 'self::X::Y'): ('src/models/risk.rs', 'X'),
        ('src/models/risk.rs', 'self::helper::X'): ('src/models/risk.rs', 'helper'),
        ('src/models/risk.rs', 'shared::X'): ('src/shared.rs', 'X'),
        ('src/models/risk.rs', 'super::super::shared::X'): ('src/shared.rs', 'X'),
        ('src/shared.rs', 'crate::X'): ('src/lib.rs', 'X'),
        ('src/shared.rs', 'crate::models::risk::Status::Active'): ('src/models/risk.rs', 'Status'),
        ('src/shared.rs', 'crate::models::risk::X'): ('src/models/risk.rs', 'X'),
        ('src/shared.rs', 'crate::shared::X'): ('src/shared.rs', 'X'),
        ('src/shared.rs', 'self::X'): ('src/shared.rs', 'X'),
        ('src/shared.rs', 'self::X::Y'): ('src/shared.rs', 'X'),
        ('src/shared.rs', 'self::helper::X'): ('src/shared.rs', 'helper'),
        ('src/shared.rs', 'shared::X'): ('src/shared.rs', 'X'),
        ('src/shared.rs', 'super::shared::X'): ('src/shared.rs', 'X'),
    }


def test_super_reaches_an_item_of_a_file_backed_parent_module(tmp_path):
    """A module can be backed by a sibling FILE: `src/models.rs` owns `models/`.

    `use super::Config` resolved only when the parent happened to be a
    `mod.rs`, so the whole file-backed half of Rust's module system missed
    every item defined in a parent.
    """
    (tmp_path / "src" / "models").mkdir(parents=True)
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "d"\n', encoding="utf-8")
    (tmp_path / "src" / "lib.rs").write_text("pub mod models;\n", encoding="utf-8")
    (tmp_path / "src" / "models.rs").write_text(
        "pub mod risk;\npub struct Config;\n", encoding="utf-8"
    )
    (tmp_path / "src" / "models" / "risk.rs").write_text(
        "use super::Config;\npub fn run() -> u32 { 1 }\n", encoding="utf-8"
    )
    result, nodes = _graph(tmp_path)
    assert ("risk.rs", "models.rs") in _edges(result, nodes, "imports_from")
    assert ("risk.rs", "Config") in _edges(result, nodes, "imports")
