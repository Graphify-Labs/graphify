"""Regression and safety coverage for Rust grouped `self` imports (#5398)."""
from __future__ import annotations

import json
from pathlib import Path

from graphify.extract import extract


def _write_fixture(
    root: Path,
    files: dict[str, str],
    cargo_toml: str | None = None,
) -> None:
    if cargo_toml is not None:
        (root / "Cargo.toml").write_text(cargo_toml, encoding="utf-8")
    for relative, body in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


def _extract_fixture(
    root: Path,
    files: dict[str, str],
    cargo_toml: str | None = None,
) -> dict:
    _write_fixture(root, files, cargo_toml)
    paths = sorted(
        root / relative
        for relative in files
        if relative.endswith(".rs")
    )
    return extract(
        paths,
        root=root,
        cache_root=root / "graphify-out",
        parallel=False,
    )


def _build_graph(root: Path) -> dict:
    from graphify.watch import _rebuild_code

    assert _rebuild_code(
        root, changed_paths=None, no_cluster=True, acquire_lock=False
    ) is True
    return json.loads(
        (root / "graphify-out" / "graph.json").read_text(encoding="utf-8")
    )


def _node_id(result: dict, source_suffix: str) -> str:
    return next(
        node["id"]
        for node in result["nodes"]
        if node.get("source_file", "").endswith(source_suffix)
        and node.get("label") == Path(source_suffix).name
    )


def _import_targets(result: dict, source_id: str, line: int) -> list[str]:
    edges = result.get("edges", result.get("links", []))
    return [
        edge["target"]
        for edge in edges
        if edge.get("source") == source_id
        and edge.get("relation") == "imports_from"
        and edge.get("source_location") == f"L{line}"
    ]


def _assert_no_dangling_extraction_edges(result: dict) -> None:
    ids = {node["id"] for node in result["nodes"]}
    dangling = [
        (edge["source"], edge["target"], edge["relation"])
        for edge in result["edges"]
        if edge["source"] not in ids or edge["target"] not in ids
    ]
    assert dangling == []


def _assert_no_dev_concept(graph: dict) -> None:
    assert not any(
        node.get("id") == "dev" and node.get("type") == "concept"
        for node in graph["nodes"]
    )


def test_regression_no_manifest_declared_module_resolves_structurally(
    tmp_path: Path,
) -> None:
    result = _extract_fixture(tmp_path, {
        "actions/src/lib.rs": "pub mod dev;\n",
        "actions/src/dev.rs": "pub struct Runner;\n",
        "actions/src/bin/b.rs": (
            "use baba_actions::dev::{self, Runner};\n"
            "fn run(_runner: Runner) {}\n"
        ),
    })

    source = _node_id(result, "actions/src/bin/b.rs")
    module = _node_id(result, "actions/src/dev.rs")
    assert module in _import_targets(result, source, 1)
    _assert_no_dangling_extraction_edges(result)
    _assert_no_dev_concept(_build_graph(tmp_path))


def test_coverage_no_manifest_undeclared_module_file_is_not_linked(
    tmp_path: Path,
) -> None:
    result = _extract_fixture(tmp_path, {
        "actions/src/lib.rs": "pub mod ports;\n",
        "actions/src/dev.rs": "pub struct Runner;\n",
        "actions/src/bin/b.rs": "use baba_actions::dev::{self};\n",
    })

    source = _node_id(result, "actions/src/bin/b.rs")
    module = _node_id(result, "actions/src/dev.rs")
    targets = _import_targets(result, source, 1)
    assert "dev" in targets
    assert module not in targets


def test_regression_cargo_package_name_with_hyphen_resolves_self_module(
    tmp_path: Path,
) -> None:
    cargo = (
        '[package]\nname = "baba-actions"\n'
        'version = "0.1.0"\nedition = "2021"\n'
    )
    result = _extract_fixture(tmp_path, {
        "src/lib.rs": "pub mod dev;\n",
        "src/dev.rs": "pub struct Runner;\n",
        "src/bin/main.rs": (
            "use baba_actions::dev::{self, Runner};\n"
            "fn run(_runner: Runner) {}\n"
        ),
    }, cargo_toml=cargo)

    source = _node_id(result, "src/bin/main.rs")
    module = _node_id(result, "src/dev.rs")
    assert module in _import_targets(result, source, 1)
    _assert_no_dangling_extraction_edges(result)
    _assert_no_dev_concept(_build_graph(tmp_path))


def test_coverage_external_serde_self_does_not_bind_local_declared_de(
    tmp_path: Path,
) -> None:
    cargo = (
        '[package]\nname = "myapp"\n'
        'version = "0.1.0"\nedition = "2021"\n'
    )
    result = _extract_fixture(tmp_path, {
        "src/lib.rs": "pub mod de;\n",
        "src/de.rs": "pub struct LocalDecoder;\n",
        "src/main.rs": "use serde::de::{self, Visitor};\n",
    }, cargo_toml=cargo)

    source = _node_id(result, "src/main.rs")
    local_de = _node_id(result, "src/de.rs")
    targets = _import_targets(result, source, 1)
    assert "de" in targets
    assert local_de not in targets


def test_coverage_unrelated_crates_are_not_guessed(
    tmp_path: Path,
) -> None:
    result = _extract_fixture(tmp_path, {
        "crate_a/Cargo.toml": (
            '[package]\nname = "crate-a"\n'
            'version = "0.1.0"\nedition = "2021"\n'
        ),
        "crate_a/src/lib.rs": "pub mod dev;\n",
        "crate_a/src/dev.rs": "pub struct A;\n",
        "crate_b/Cargo.toml": (
            '[package]\nname = "crate-b"\n'
            'version = "0.1.0"\nedition = "2021"\n'
        ),
        "crate_b/src/lib.rs": "pub mod dev;\n",
        "crate_b/src/dev.rs": "pub struct B;\n",
        "consumer/src/lib.rs": "pub fn consumer() {}\n",
        "consumer/src/main.rs": "use baba_actions::dev::{self};\n",
    })

    source = _node_id(result, "consumer/src/main.rs")
    local_modules = {
        _node_id(result, "crate_a/src/dev.rs"),
        _node_id(result, "crate_b/src/dev.rs"),
    }
    targets = _import_targets(result, source, 1)
    assert "dev" in targets
    assert not (local_modules & set(targets))


def test_regression_self_as_alias_targets_original_module_file(
    tmp_path: Path,
) -> None:
    result = _extract_fixture(tmp_path, {
        "src/lib.rs": (
            "pub mod dev;\n"
            "use crate::dev::{self as runtime};\n"
        ),
        "src/dev.rs": "pub struct Runner;\n",
    })

    source = _node_id(result, "src/lib.rs")
    module = _node_id(result, "src/dev.rs")
    assert module in _import_targets(result, source, 2)
    _assert_no_dangling_extraction_edges(result)
    _assert_no_dev_concept(_build_graph(tmp_path))


def test_regression_crate_and_super_self_groups_target_module_file(
    tmp_path: Path,
) -> None:
    result = _extract_fixture(tmp_path, {
        "src/lib.rs": (
            "pub mod dev;\n"
            "pub mod nested;\n"
            "use crate::dev::{self};\n"
        ),
        "src/dev.rs": "pub struct Runner;\n",
        "src/nested.rs": "use super::dev::{self};\n",
    })

    module = _node_id(result, "src/dev.rs")
    lib = _node_id(result, "src/lib.rs")
    nested = _node_id(result, "src/nested.rs")
    assert module in _import_targets(result, lib, 3)
    assert module in _import_targets(result, nested, 1)
    _assert_no_dangling_extraction_edges(result)
    _assert_no_dev_concept(_build_graph(tmp_path))


def test_regression_cargo_self_group_resolves_dev_mod_rs(
    tmp_path: Path,
) -> None:
    cargo = (
        '[package]\nname = "baba-actions"\n'
        'version = "0.1.0"\nedition = "2021"\n'
    )
    result = _extract_fixture(tmp_path, {
        "src/lib.rs": "pub mod dev;\n",
        "src/dev/mod.rs": "pub struct Runner;\n",
        "src/bin/main.rs": (
            "use baba_actions::dev::{self, Runner};\n"
            "fn run(_runner: Runner) {}\n"
        ),
    }, cargo_toml=cargo)

    source = _node_id(result, "src/bin/main.rs")
    module = _node_id(result, "src/dev/mod.rs")
    assert module in _import_targets(result, source, 1)
    _assert_no_dangling_extraction_edges(result)
    _assert_no_dev_concept(_build_graph(tmp_path))


def test_regression_nested_cargo_path_does_not_match_other_dev_file(
    tmp_path: Path,
) -> None:
    cargo = (
        '[package]\nname = "myapp"\n'
        'version = "0.1.0"\nedition = "2021"\n'
    )
    result = _extract_fixture(tmp_path, {
        "src/lib.rs": "pub mod a;\nuse crate::a::dev::{self};\n",
        "src/a.rs": "pub mod dev;\n",
        "src/other/dev.rs": "pub struct WrongModule;\n",
    }, cargo_toml=cargo)

    source = _node_id(result, "src/lib.rs")
    other_dev = _node_id(result, "src/other/dev.rs")
    targets = _import_targets(result, source, 2)
    assert "dev" in targets
    assert other_dev not in targets


def test_regression_nested_cargo_path_resolves_declared_module_file(
    tmp_path: Path,
) -> None:
    cargo = (
        '[package]\nname = "myapp"\n'
        'version = "0.1.0"\nedition = "2021"\n'
    )
    result = _extract_fixture(tmp_path, {
        "src/lib.rs": "pub mod a;\nuse crate::a::dev::{self};\n",
        "src/a.rs": "pub mod dev;\n",
        "src/a/dev.rs": "pub struct Runner;\n",
    }, cargo_toml=cargo)

    source = _node_id(result, "src/lib.rs")
    module = _node_id(result, "src/a/dev.rs")
    assert module in _import_targets(result, source, 2)
    _assert_no_dangling_extraction_edges(result)
    _assert_no_dev_concept(_build_graph(tmp_path))


def test_regression_issue_four_file_reproduction_and_sibling_imports(
    tmp_path: Path,
) -> None:
    result = _extract_fixture(tmp_path, {
        "actions/src/lib.rs": (
            "pub mod dev;\n"
            "pub mod ports;\n"
            "pub use ports::Intent;\n"
        ),
        "actions/src/dev.rs": (
            "pub struct SystemRunner;\n"
            "pub fn build() {}\n"
        ),
        "actions/src/ports.rs": (
            "pub trait Console {\n"
            "    fn out(&self, line: &str);\n"
            "}\n"
            "pub struct SystemConsole;\n"
            "pub struct Intent;\n"
        ),
        "actions/src/bin/b.rs": (
            "use baba_actions::Intent;\n"
            "use baba_actions::dev::{self, SystemRunner};\n"
            "use baba_actions::ports::{Console, SystemConsole};\n"
            "\n"
            "fn run(c: &dyn Console, _i: &Intent, "
            "_s: SystemConsole, _r: SystemRunner) {\n"
            "    c.out(\"hi\");\n"
            "    dev::build();\n"
            "}\n"
            "\n"
            "fn main() {}\n"
        ),
    })

    source = _node_id(result, "actions/src/bin/b.rs")
    expected = {
        "actions_src_dev",
        "actions_src_ports_console",
        "actions_src_ports_systemconsole",
        "actions_src_ports_intent",
    }
    targets = {
        target
        for line in (1, 2, 3)
        for target in _import_targets(result, source, line)
    }
    assert expected <= targets
    assert "dev" not in targets
    _assert_no_dangling_extraction_edges(result)
    _assert_no_dev_concept(_build_graph(tmp_path))
