"""A Rust `use` tree imports what the plain `use` of each of its bindings would.

extract_rust cut a `use` at its first `{` and kept one segment, so
`use crate::util::{parse, render};` became one `imports_from` edge to a `util`
stub and `use {a::b, c};` none at all. Each binding of a tree now gets the edge
v8 emits for the equivalent plain `use` (`use crate::util::parse;` and
`use crate::util::render;`), from the same file node and on the binding's line.
Plain `use` declarations are unchanged, and so are call edges: v8's edge for a
group still serves the call pass, which does not see the new ones.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import graphify.extractors.rust as rust_module
from graphify.extract import extract

_CARGO = '[package]\nname = "demo"\nversion = "0.1.0"\nedition = "2021"\n'
_FILES = {"src/lib.rs": "pub mod util;\npub mod user;\n", "src/util.rs": "pub fn parse() {}\npub fn render() {}\n"}


def _write(root: Path, files: dict[str, str]) -> None:
    for name, body in {"Cargo.toml": _CARGO, **files}.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(body, encoding="utf-8")


def _extract(root: Path, files: dict[str, str]) -> dict:
    _write(root, files)
    paths = sorted(root / name for name in files if name.endswith(".rs"))
    return extract(paths, root=root, cache_root=root / "graphify-out", parallel=False)


def _build(root: Path, changed: list[Path] | None = None) -> dict:
    from graphify.watch import _rebuild_code

    assert _rebuild_code(root, changed_paths=changed, no_cluster=True, acquire_lock=False) is True
    return json.loads((root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))


def _edges(edges: list[dict], kind: str = "import") -> list[str]:
    return sorted(json.dumps(e, sort_keys=True) for e in edges if e.get("context") == kind)


# name: (the tree, and the same bindings as plain `use` declarations on the
# same lines). Each pair must give the same edges and nodes.
SHAPES = {
    "group": ("use crate::util::{parse, render};\n", "use crate::util::parse; use crate::util::render;\n"),
    "nested": ("use crate::{util::{parse, render}, lib};\n",
               "use crate::util::parse; use crate::util::render; use crate::lib;\n"),
    "self": ("use crate::util::{self, parse};\n", "use crate::util; use crate::util::parse;\n"),
    "self_alias": ("use crate::util::{self as u};\n", "use crate::util as u;\n"),
    "alias": ("use crate::util::{parse as p, render};\n", "use crate::util::parse as p; use crate::util::render;\n"),
    "alias_comment": ("use crate::util::{parse /* note */ as p};\n", "use crate::util::parse /* note */ as p;\n"),
    "alias_after_as_comment": ("use crate::util::{parse as /* note */ p};\n", "use crate::util::parse as /* note */ p;\n"),
    "self_alias_comment": ("use crate::util::{self /* note */ as u};\n", "use crate::util /* note */ as u;\n"),
    "spaced_glob_delimiter": ("use crate::util :: {*};\n", "use crate::util :: *;\n"),
    "self_delimiter_comment": ("use crate::util /* note */ :: {self};\n", "use crate::util;\n"),
    "nested_self_prefix_comment": ("use crate::/* note */{util::{self}};\n", "use crate::/* note */util;\n"),
    "nested_glob_prefix_comment": ("use crate::/* note */{util::{*}};\n", "use crate::/* note */util::*;\n"),
    "nested_prefix_brace_comment": ("use crate::/* { */util::{nested::{parse}};\n", "use crate::/* { */util::nested::parse;\n"),
    "glob": ("use crate::{util::*, lib};\n", "use crate::util::*; use crate::lib;\n"),
    "glob_alone": ("use crate::util::{*};\n", "use crate::util::*;\n"),
    "root_group": ("use {crate::util::parse, std::io};\n", "use crate::util::parse; use std::io;\n"),
    "leading_colons": ("use ::std::{io, fmt::Write};\n", "use ::std::io; use ::std::fmt::Write;\n"),
    "root_colons": ("use ::{std::io};\n", "use ::std::io;\n"),
    "braces": ("use std::{{self}, {io::*}};\n", "use std; use std::io::*;\n"),
    "super": ("use super::{util, lib::Thing};\n", "use super::util; use super::lib::Thing;\n"),
    "pub": ("pub use self::{a::B, c};\n", "pub use self::a::B; pub use self::c;\n"),
    "raw": ("use crate::{r#match, util::r#type};\n", "use crate::r#match; use crate::util::r#type;\n"),
    "comments": ("use crate::util::{/* first */ parse, // second\nrender, a::/* in */b};\n",
                 "use crate::util::parse;\nuse crate::util::render; use crate::util::a::/* in */b;\n"),
    "spacing": ("use crate :: util::{ parse  as  p , render };\n", "use crate :: util::parse  as  p; use crate :: util::render;\n"),
    "lines": ("use crate::util::{\n    parse,\n    render as draw,\n};\n",
              "\nuse crate::util::parse;\nuse crate::util::render as draw;\n\n"),
}


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_a_tree_imports_what_its_plain_list_does(tmp_path: Path, name: str):
    tree, plain = SHAPES[name]
    assert tree.count("\n") == plain.count("\n")
    graphs = {}
    for form, text in (("tree", tree), ("plain", plain)):
        root = tmp_path / form
        result = _extract(root, {**_FILES, "src/user.rs": text + "pub fn run() {}\n"})
        graphs[form] = (_edges(result["edges"]), sorted(json.dumps(n, sort_keys=True) for n in result["nodes"]),
                        _build(root))
    assert graphs["tree"][:2] == graphs["plain"][:2]
    persisted = {form: (_edges(graph["links"]), sorted(json.dumps(n, sort_keys=True) for n in graph["nodes"]))
                 for form, (_e, _n, graph) in graphs.items()}
    assert persisted["tree"] == persisted["plain"]


def test_each_binding_gets_the_plain_use_target(tmp_path: Path):
    result = _extract(tmp_path, {**_FILES, "src/user.rs": (
        "use crate::util::{self, parse, render as draw, nested::{deep, *}};\nuse {a::b, c};\n"
        "use crate::util::parse;\nuse std::io::Read;\nuse foo::bar as baz;\nuse crate::util::*;\npub use\n    std::fmt;\n")})
    edges = sorted((e["relation"], e["target"], e["source_location"]) for e in result["edges"]
                   if e.get("context") == "import")
    assert edges == sorted([
        ("imports_from", "util", "L1"), ("imports_from", "parse", "L1"), ("imports_from", "render_as_draw", "L1"),
        ("imports_from", "deep", "L1"), ("imports_from", "nested", "L1"), ("imports_from", "b", "L2"),
        ("imports_from", "c", "L2"),
        # plain declarations, exactly as v8 emits them
        ("imports_from", "parse", "L3"), ("imports_from", "read", "L4"), ("imports_from", "bar_as_baz", "L5"),
        ("imports_from", "util", "L6"), ("imports_from", "fmt", "L7")])
    sources = {e["source"] for e in result["edges"] if e.get("context") == "import"}
    file_node = next(n["id"] for n in result["nodes"] if n.get("label") == "user.rs")
    assert sources == {file_node}
    assert all(e["source_file"].endswith("user.rs") for e in result["edges"] if e.get("context") == "import")
    assert not any(k.startswith("_rust_use") for e in result["edges"] for k in e)


def test_a_file_whose_only_use_is_a_root_group_gets_edges_from_its_file_node(tmp_path: Path):
    # v8 emitted nothing for `use {..};`.
    result = _extract(tmp_path, {**_FILES, "src/user.rs": "use {crate::util::parse, std::io};\n"})
    file_node = next(n["id"] for n in result["nodes"] if n.get("label") == "user.rs")
    assert sorted((e["source"], e["target"]) for e in result["edges"] if e.get("context") == "import") == [
        (file_node, "io"), (file_node, "parse")]


# Files at the scan root, so file node ids are bare stems: the binding `util`
# names util.rs's file node, which v8's group edge (`crate`) never did. Were
# the binding call evidence, run() -> helper() would be promoted to EXTRACTED.
_CALLS = {"lib.rs": "pub mod util;\npub mod user;\npub mod other;\n",
          "util.rs": "pub fn helper() {}\npub fn shared() {}\n", "other.rs": "pub fn shared() {}\n",
          "user.rs": "use crate::{util, other::Thing};\npub fn run() { helper(); shared(); }\n"}


def test_calls_are_the_ones_v8_finds(tmp_path: Path, monkeypatch):
    def calls(root: Path) -> list[str]:
        result = extract(sorted(root / name for name in _CALLS), root=root, cache_root=root / "out", parallel=False)
        return sorted(json.dumps({k: e.get(k) for k in ("source", "target", "relation", "confidence",
                                                       "confidence_score", "source_location")}, sort_keys=True)
                      for e in result["edges"] if e.get("context") in ("call", "constructor"))

    for name, body in _CALLS.items():
        for form in ("fix", "v8"):
            (tmp_path / form / name).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / form / name).write_text(body, encoding="utf-8")
    fixed = calls(tmp_path / "fix")
    monkeypatch.setattr(rust_module, "_rust_use_bindings", lambda *args: [])  # v8: no binding edges
    assert fixed and fixed == calls(tmp_path / "v8")


def _parity(tmp_path: Path, monkeypatch, steps: list) -> None:
    """Build, then apply each change: watch and `graphify extract` equal a full build."""
    import graphify.__main__ as mainmod

    def cli(root: Path) -> dict:
        monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
        monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "extract", str(root), "--code-only", "--no-cluster"])
        try:
            mainmod.main()
        except SystemExit as exc:
            assert exc.code in (None, 0)
        return json.loads((root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))

    def view(graph: dict) -> tuple:
        # v8 keeps external stubs across incremental builds (unreferenced ones too)
        # and stamps them `semantic` on reload; compare the rest exactly.
        return (sorted(json.dumps(e, sort_keys=True) for e in graph.get("links", graph.get("edges", []))),
                sorted(json.dumps(n, sort_keys=True) for n in graph["nodes"] if not n.get("external")))

    files = {**_FILES, "src/user.rs": "use crate::util::{parse, render};\n", "src/other.rs": "use crate::util::parse;\n"}
    for mode in ("watch", "extract"):
        root = tmp_path / mode
        _write(root, files)
        _build(root) if mode == "watch" else cli(root)
        for number, (name, text) in enumerate(steps):
            (root / name).write_text(text, encoding="utf-8")
            incremental = _build(root, [root / name]) if mode == "watch" else cli(root)
            fresh = tmp_path / f"{mode}-fresh-{number}"
            _write(fresh, {path: (root / path).read_text(encoding="utf-8") for path in files})
            assert view(incremental) == view(_build(fresh) if mode == "watch" else cli(fresh)), (mode, name)


def test_incremental_builds_match_full_builds(tmp_path: Path, monkeypatch):
    _parity(tmp_path, monkeypatch, [
        ("src/user.rs", "use crate::util::{parse, render as draw, self};\n"),  # grouped edited
        ("src/other.rs", "use {crate::util::render, std::io};\n"),  # plain becomes a root group
        ("src/user.rs", "use crate::util::parse;\n"),  # group becomes plain
    ])


def test_a_cache_entry_from_before_the_bindings_is_not_served(tmp_path: Path, monkeypatch):
    import graphify.cache as cache_mod
    from graphify.cache import save_cached

    files = {**_FILES, "src/user.rs": "use crate::util::{parse, render};\n"}
    _write(tmp_path, files)
    path = tmp_path / "src" / "user.rs"
    current = cache_mod._AST_CACHE_SCHEMA
    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", 6)  # v0.9.80's
    with monkeypatch.context() as patch:
        patch.setattr(rust_module, "_rust_use_bindings", lambda *args: [])  # what v8 cached
        stale = rust_module.extract_rust(path)
    for edge in stale["edges"]:
        edge.pop("_rust_use_group", None)
    save_cached(path, stale, tmp_path, cache_root=tmp_path / "graphify-out")
    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", current)
    result = extract(sorted(tmp_path / name for name in files), root=tmp_path, cache_root=tmp_path / "graphify-out",
                     parallel=False)
    assert sorted(e["target"] for e in result["edges"]
                  if e.get("context") == "import" and e["source_file"].endswith("user.rs")) == ["parse", "render"]
