"""A Rust `use` from another crate does not land on a same-named local definition.

A reference to `Value` is a sourceless stub, and the corpus rewire bound it to the
only `Value` in the corpus — even when the file said `use serde_json::Value` and
the local `Value` was a struct field. The rewire now reads the crate a stub's
`use` names: `serde_json` is outside the scanned crates, so the stub stays
unbound; `a::Value` in a workspace where `a` is scanned reaches `a`'s definition
and not a namesake elsewhere. A stub is only scoped when its file is under a
Cargo.toml, so each fixture writes one per crate; a manifest-less `.rs` scan
keeps the old label-only binding, which the rewire flags as INFERRED instead of
silently presenting it as EXTRACTED (#4699).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.extract import extract

ENUM_A = "pub enum Field {\n    Value(String),\n}\n"
STRUCT_VALUE = "pub struct Value;\n"
USE_VALUE = 'pub fn get(v: &Value) -> Option<&Value> {\n    v.get("x")\n}\n'


def _write(root: Path, files: dict[str, str], manifests: bool = True) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    if not manifests:
        return
    for crate in {rel.split("/")[0] for rel in files if rel.endswith(".rs")}:
        manifest = root / crate / "Cargo.toml"
        if not manifest.exists():
            manifest.write_text(f'[package]\nname = "{crate}"\n', encoding="utf-8")


def _run(tmp_path: Path, files: dict[str, str], manifests: bool = True) -> dict:
    _write(tmp_path, files, manifests)
    paths = sorted(tmp_path.rglob("*.rs"))
    return extract(paths, root=tmp_path, cache_root=tmp_path / "cache", parallel=False)


def _crate(root: Path, source_file: str | None) -> str | None:
    if not source_file:
        return None
    path = Path(source_file)
    rel = path.relative_to(root) if path.is_absolute() else path
    return rel.parts[0]


def _edges_between(result: dict, root: Path, src_crate: str, dst_crate: str) -> list[dict]:
    """Non-structural edges from a node in `src_crate` to a node in `dst_crate`."""
    nodes = {n["id"]: n for n in result["nodes"]}
    return [
        edge
        for edge in result["edges"]
        if edge["relation"] not in ("contains", "case_of", "method")
        and _crate(root, nodes.get(edge["source"], {}).get("source_file")) == src_crate
        and _crate(root, nodes.get(edge["target"], {}).get("source_file")) == dst_crate
    ]


@pytest.mark.parametrize("decl", [ENUM_A, STRUCT_VALUE], ids=["variant", "struct"])
def test_external_crate_use_and_annotation_do_not_reach_a_local_crate(tmp_path, decl):
    result = _run(tmp_path, {
        "a/src/lib.rs": decl,
        "b/src/lib.rs": "use serde_json::Value;\n\n" + USE_VALUE,
    })
    assert _edges_between(result, tmp_path, "b", "a") == []


def test_external_crate_use_alone_does_not_reach_a_local_crate(tmp_path):
    result = _run(tmp_path, {
        "a/src/lib.rs": ENUM_A,
        "b/src/lib.rs": "use serde_json::Value;\n\npub fn f() {}\n",
    })
    assert _edges_between(result, tmp_path, "b", "a") == []


def test_annotation_without_any_use_does_not_reach_a_local_crate(tmp_path):
    result = _run(tmp_path, {"a/src/lib.rs": ENUM_A, "b/src/lib.rs": USE_VALUE})
    assert _edges_between(result, tmp_path, "b", "a") == []


def test_std_use_does_not_reach_a_same_named_local_struct(tmp_path):
    result = _run(tmp_path, {
        "a/src/lib.rs": "pub struct HashMap;\n",
        "b/src/lib.rs": "use std::collections::HashMap;\n\npub fn f(m: &HashMap<u8, u8>) {}\n",
    })
    assert _edges_between(result, tmp_path, "b", "a") == []


def test_grouped_external_use_does_not_reach_a_local_crate(tmp_path):
    result = _run(tmp_path, {
        "a/src/lib.rs": ENUM_A + "pub struct Map;\n",
        "b/src/lib.rs": "use serde_json::{Map, Value};\n\npub fn f(m: &Map<String, Value>) {}\n",
    })
    assert _edges_between(result, tmp_path, "b", "a") == []


def test_workspace_crate_use_reaches_that_crate(tmp_path):
    result = _run(tmp_path, {
        "a/src/lib.rs": STRUCT_VALUE,
        "b/src/lib.rs": "use a::Value;\n\n" + USE_VALUE,
        "b/Cargo.toml": '[package]\nname = "b"\n\n[dependencies]\na = { path = "../a" }\n',
    })
    assert _edges_between(result, tmp_path, "b", "a") != []


def test_workspace_crate_use_reaches_the_named_crate_not_a_namesake(tmp_path):
    result = _run(tmp_path, {
        "a/src/lib.rs": STRUCT_VALUE,
        "c/src/lib.rs": STRUCT_VALUE,
        "b/src/lib.rs": "use a::Value;\n\n" + USE_VALUE,
    })
    assert _edges_between(result, tmp_path, "b", "a") != []
    assert _edges_between(result, tmp_path, "b", "c") == []


def test_workspace_crate_use_does_not_reach_another_crates_namesake(tmp_path):
    # `osiris_types` (package `osiris-types`) has no `Config`; `server` has one.
    result = _run(tmp_path, {
        "osiris-types/src/lib.rs": "pub struct Other;\n",
        "server/src/lib.rs": "pub struct Config;\n",
        "plugin/src/lib.rs": "use osiris_types::Config;\n\npub fn f(c: &Config) {}\n",
    })
    assert _edges_between(result, tmp_path, "plugin", "server") == []


def test_workspace_crate_use_reaches_its_own_crate_when_two_crates_share_a_name(tmp_path):
    result = _run(tmp_path, {
        "osiris-types/src/lib.rs": "pub struct Config;\n",
        "server/src/lib.rs": "pub struct Config;\n",
        "plugin/src/lib.rs": "use osiris_types::Config;\n\npub fn f(c: &Config) {}\n",
    })
    assert _edges_between(result, tmp_path, "plugin", "osiris-types") != []
    assert _edges_between(result, tmp_path, "plugin", "server") == []


def test_crate_relative_use_reaches_its_own_module(tmp_path):
    result = _run(tmp_path, {
        "b/src/lib.rs": "mod model;\nuse crate::model::Value;\n\n" + USE_VALUE,
        "b/src/model.rs": STRUCT_VALUE,
    })
    assert _edges_between(result, tmp_path, "b", "b") != []


def test_same_named_types_in_two_crates_have_no_edge_without_a_use(tmp_path):
    result = _run(tmp_path, {"a/src/lib.rs": STRUCT_VALUE, "b/src/lib.rs": STRUCT_VALUE})
    assert _edges_between(result, tmp_path, "a", "b") == []
    assert _edges_between(result, tmp_path, "b", "a") == []


def test_a_crate_less_binding_is_flagged_inferred_not_extracted(tmp_path):
    # No Cargo.toml anywhere: there is no crate to scope the external `use` by, so
    # the rewire still binds by label and must say it is guessing.
    result = _run(
        tmp_path,
        {"a/src/lib.rs": STRUCT_VALUE, "b/src/lib.rs": "use serde_json::Value;\n\n" + USE_VALUE},
        manifests=False,
    )
    edges = _edges_between(result, tmp_path, "b", "a")
    assert edges
    assert {edge["confidence"] for edge in edges} == {"INFERRED"}


def test_a_use_of_this_crate_keeps_the_binding_extracted(tmp_path):
    result = _run(tmp_path, {
        "b/src/lib.rs": "mod model;\nuse crate::model::Value;\n\n" + USE_VALUE,
        "b/src/model.rs": STRUCT_VALUE,
    })
    edges = _edges_between(result, tmp_path, "b", "b")
    assert {edge["confidence"] for edge in edges} == {"EXTRACTED"}


def test_a_use_of_a_reexporting_crate_reaches_the_defining_crate(tmp_path):
    # `api` re-exports `corelib`'s type, as axum re-exports axum-core's.
    result = _run(tmp_path, {
        "corelib/src/lib.rs": "pub struct FromRequestParts;\n",
        "api/src/lib.rs": "pub use corelib::FromRequestParts;\n",
        "plugin/src/lib.rs": "use api::FromRequestParts;\n\npub fn f(x: &FromRequestParts) {}\n",
    })
    assert _edges_between(result, tmp_path, "plugin", "corelib") != []


def test_a_reexport_does_not_reach_an_unrelated_namesake(tmp_path):
    result = _run(tmp_path, {
        "corelib/src/lib.rs": "pub struct FromRequestParts;\n",
        "other/src/lib.rs": "pub struct FromRequestParts;\n",
        "api/src/lib.rs": "pub use corelib::FromRequestParts;\n",
        "plugin/src/lib.rs": "use api::FromRequestParts;\n\npub fn f(x: &FromRequestParts) {}\n",
    })
    assert _edges_between(result, tmp_path, "plugin", "corelib") != []
    assert _edges_between(result, tmp_path, "plugin", "other") == []


def test_a_super_use_of_a_reexported_type_reaches_the_defining_crate(tmp_path):
    # axum/src/extract/connect_info.rs: `use super::{.., FromRequestParts}` where the
    # parent module re-exports an axum-core type.
    result = _run(tmp_path, {
        "corelib/src/lib.rs": "pub struct FromRequestParts;\n",
        "api/src/lib.rs": "pub mod sub;\npub use corelib::FromRequestParts;\n",
        "api/src/sub.rs": "use super::FromRequestParts;\n\npub fn f(x: &FromRequestParts) {}\n",
    })
    assert _edges_between(result, tmp_path, "api", "corelib") != []


def test_a_crate_restricted_reexport_does_not_leak_out_of_its_crate(tmp_path):
    # `pub(crate) use` is not visible to another crate, so the name stays unbound.
    result = _run(tmp_path, {
        "corelib/src/lib.rs": "pub struct FromRequestParts;\n",
        "api/src/lib.rs": "pub(crate) use corelib::FromRequestParts;\n",
        "plugin/src/lib.rs": "use api::FromRequestParts;\n\npub fn f(x: &FromRequestParts) {}\n",
    })
    assert _edges_between(result, tmp_path, "plugin", "corelib") == []


def test_a_use_of_a_scanned_crate_keeps_the_binding_extracted(tmp_path):
    result = _run(tmp_path, {
        "corelib/src/lib.rs": "pub struct FromRequestParts;\n",
        "plugin/src/lib.rs": (
            "use corelib::FromRequestParts;\n\npub fn f(x: &FromRequestParts) {}\n"
        ),
    })
    edges = _edges_between(result, tmp_path, "plugin", "corelib")
    assert edges
    assert {edge["confidence"] for edge in edges} == {"EXTRACTED"}
