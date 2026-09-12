"""Rust module-qualified calls resolve cross-file, verified by the qualifier (#908).

Scoped calls (`module::function()`) — the dominant intra-crate call form in
idiomatic Rust — used to be dropped at extraction: bare last-segment lookup
across crates produced spurious INFERRED edges (#908), so a real production
caller showed 0 dependents while grep found the call site immediately.

The resolver keeps the #908 guard but uses the discarded qualifier as the
verification key: the last segment must BE the defining module (`<seg>.rs` or
`<seg>/mod.rs`), every remaining segment must match the successive parent
directory (stopping at `crate`/`super`/`self`), candidates are Rust-only, and
a qualifier bound by a `use` from outside the crate is skipped at extraction.
Exactly one survivor or no edge.

These tests pin: the resolution positives (plain, `mod.rs`, crate-qualified,
use-bound from the crate), the std-shadowing and cross-language false
positives, and the guards (ambiguity, uppercase types, bare `super`/`self`,
untouched bare-name path).
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _calls(files: list[Path], base: Path) -> set[tuple[str, str, str]]:
    r = extract(files, cache_root=base, parallel=False)
    # Rust function labels carry their call parens (`run()`); strip for
    # comparison so assertions read as source names.
    lbl = {n["id"]: n["label"].strip("()") for n in r["nodes"]}
    return {
        (lbl.get(e["source"], ""), lbl.get(e["target"], ""), e.get("confidence"))
        for e in r["edges"] if e["relation"] == "calls"
    }


def test_module_qualified_call_resolves_to_the_named_module(tmp_path: Path) -> None:
    _write(tmp_path / "src/a.rs",
           "pub fn run() { b::helper(); }\n")
    _write(tmp_path / "src/b.rs",
           "pub fn helper() {}\n")
    # c.rs defines a same-named helper → the qualifier, not the name, decides
    _write(tmp_path / "src/c.rs",
           "pub fn helper() {}\n")
    calls = _calls(sorted(tmp_path.rglob("*.rs")), tmp_path)
    assert ("run", "helper", "EXTRACTED") in calls, calls


def test_mod_rs_form_resolves(tmp_path: Path) -> None:
    _write(tmp_path / "src/a.rs",
           "pub fn run() { util::helper(); }\n")
    _write(tmp_path / "src/util/mod.rs",
           "pub fn helper() {}\n")
    calls = _calls(sorted(tmp_path.rglob("*.rs")), tmp_path)
    assert ("run", "helper", "EXTRACTED") in calls, calls


def test_two_matching_module_files_emit_nothing(tmp_path: Path) -> None:
    # helper() in both b.rs and b/mod.rs → two survivors → skipped (god-node guard)
    _write(tmp_path / "src/a.rs",
           "pub fn run() { b::helper(); }\n")
    _write(tmp_path / "src/b.rs",
           "pub fn helper() {}\n")
    _write(tmp_path / "src/b/mod.rs",
           "pub fn helper() {}\n")
    calls = _calls(sorted(tmp_path.rglob("*.rs")), tmp_path)
    assert not any(s == "run" and t == "helper" for s, t, _ in calls), calls


def test_uppercase_qualifier_is_a_type_not_a_module(tmp_path: Path) -> None:
    # Uppercase qualifier is a type (`Type::method()`) → keeps the old skipped behavior
    _write(tmp_path / "src/a.rs",
           "pub fn run() { Helper::helper(); }\n")
    _write(tmp_path / "src/helper.rs",
           "pub struct Helper;\n"
           "impl Helper { pub fn helper() {} }\n"
           "pub fn helper() {}\n")
    calls = _calls(sorted(tmp_path.rglob("*.rs")), tmp_path)
    assert not any(s == "run" for s, _t, _ in calls), calls


def test_crate_qualified_path_verifies_against_directories(tmp_path: Path) -> None:
    # Segments right of `crate` verify against directories → resolves without a module tree
    _write(tmp_path / "src/a.rs",
           "pub fn run() { crate::util::helper(); }\n")
    _write(tmp_path / "src/util.rs",
           "pub fn helper() {}\n")
    calls = _calls(sorted(tmp_path.rglob("*.rs")), tmp_path)
    assert ("run", "helper", "EXTRACTED") in calls, calls


def test_bare_super_and_self_are_skipped(tmp_path: Path) -> None:
    # Bare `super::`/`self::` names no module file → needs a module tree → skipped
    _write(tmp_path / "src/a.rs",
           "pub fn run() { super::helper(); self::helper2(); }\n")
    _write(tmp_path / "src/b.rs",
           "pub fn helper() {}\npub fn helper2() {}\n")
    calls = _calls(sorted(tmp_path.rglob("*.rs")), tmp_path)
    assert not any(s == "run" for s, _t, _ in calls), calls


def test_std_qualified_call_does_not_bind_to_local_shadow(tmp_path: Path) -> None:
    # `std::fs::read(...)` with an unrelated local fs.rs defining read →
    # the directory walk fails on `std` vs `src` → no edge
    _write(tmp_path / "src/a.rs",
           'pub fn run() { let _ = std::fs::read("x"); }\n')
    _write(tmp_path / "src/fs.rs",
           "pub fn read(p: &str) -> Vec<u8> { Vec::new() }\n")
    calls = _calls(sorted(tmp_path.rglob("*.rs")), tmp_path)
    assert not any(s == "run" and t == "read" for s, t, _ in calls), calls


def test_use_bound_qualifier_from_std_is_skipped(tmp_path: Path) -> None:
    # `use std::fs; fs::read()` → the qualifier names std's fs, not the
    # unrelated local fs.rs → skipped at enqueue
    _write(tmp_path / "src/a.rs",
           "use std::fs;\n"
           'pub fn run() { let _ = fs::read("x"); }\n')
    _write(tmp_path / "src/fs.rs",
           "pub fn read(p: &str) -> Vec<u8> { Vec::new() }\n")
    calls = _calls(sorted(tmp_path.rglob("*.rs")), tmp_path)
    assert not any(s == "run" and t == "read" for s, t, _ in calls), calls


def test_use_bound_qualifier_from_crate_still_resolves(tmp_path: Path) -> None:
    # `use crate::util;` binds util from inside the crate → still resolves
    _write(tmp_path / "src/a.rs",
           "use crate::util;\n"
           "pub fn run() { util::helper(); }\n")
    _write(tmp_path / "src/util.rs",
           "pub fn helper() {}\n")
    calls = _calls(sorted(tmp_path.rglob("*.rs")), tmp_path)
    assert ("run", "helper", "EXTRACTED") in calls, calls


def test_rust_scoped_call_cannot_bind_across_languages(tmp_path: Path) -> None:
    # Rust `b::helper()` with a Python b.py defining helper → candidates are
    # Rust-only → no cross-language edge
    _write(tmp_path / "src/a.rs",
           "pub fn run() { b::helper(); }\n")
    _write(tmp_path / "src/b.py",
           "def helper():\n    pass\n")
    files = sorted(tmp_path.rglob("*.rs")) + sorted(tmp_path.rglob("*.py"))
    calls = _calls(files, tmp_path)
    assert not any(s == "run" and t == "helper" for s, t, _ in calls), calls


def test_bare_name_calls_keep_their_existing_resolution(tmp_path: Path) -> None:
    # Control: bare-name calls keep their existing INFERRED resolution
    _write(tmp_path / "src/a.rs",
           "pub fn run() { helper(); }\n")
    _write(tmp_path / "src/b.rs",
           "pub fn helper() {}\n")
    calls = _calls(sorted(tmp_path.rglob("*.rs")), tmp_path)
    assert any(s == "run" and t == "helper" for s, t, _ in calls), calls
