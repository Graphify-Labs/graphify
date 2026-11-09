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


def _scoped_calls(tmp_path, files: dict[str, str]) -> set[tuple[str, str]]:
    paths = []
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    result = extract(paths, root=tmp_path, cache_root=tmp_path / "cache")
    node = {n["id"]: n for n in result["nodes"]}

    def where(nid: str) -> str:
        n = node.get(nid, {})
        sf = Path(n.get("source_file", ""))
        rel = (sf.relative_to(tmp_path) if sf.is_absolute() else sf).as_posix()
        return f'{rel}:{n.get("label")}'

    return {
        (where(e["source"]), where(e["target"]))
        for e in result["edges"]
        if e["relation"] == "calls" and e["target"] in node and e["source"] in node
    }


def test_crate_path_does_not_cross_into_another_workspace_crate(tmp_path):
    calls = _scoped_calls(tmp_path, {
        "crate_a/Cargo.toml": "[package]\nname = \"a\"\n",
        "crate_a/src/main.rs": "mod util;\nfn run() { crate::util::f(); }\n",
        "crate_a/src/util.rs": "pub fn g() {}\n",
        "crate_b/Cargo.toml": "[package]\nname = \"b\"\n",
        "crate_b/src/util.rs": "pub fn f() {}\n",
    })
    assert not any(tgt.startswith("crate_b/") for _, tgt in calls)


def test_module_path_never_names_an_impl_method(tmp_path):
    calls = _scoped_calls(tmp_path, {
        "Cargo.toml": "[package]\nname = \"s\"\n",
        "src/store.rs": "pub struct Db;\nimpl Db { pub fn open(&self) {} }\n",
        "src/main.rs": "mod store;\nfn run() { store::open(); }\n",
    })
    assert not any(src.endswith("run()") for src, _ in calls)


def test_underscore_module_resolves(tmp_path):
    calls = _scoped_calls(tmp_path, {
        "Cargo.toml": "[package]\nname = \"u\"\n",
        "src/_internal.rs": "pub fn helper() {}\n",
        "src/main.rs": "mod _internal;\nfn run() { crate::_internal::helper(); }\n",
    })
    assert ("src/main.rs:run()", "src/_internal.rs:helper()") in calls


def test_path_call_does_not_bind_to_a_same_named_local_function(tmp_path):
    calls = _scoped_calls(tmp_path, {
        "Cargo.toml": "[package]\nname = \"p\"\n",
        "src/a.rs": "fn helper() {}\nfn run() { crate::b::helper(); }\n",
        "src/b.rs": "pub fn helper() {}\n",
    })
    assert ("src/a.rs:run()", "src/b.rs:helper()") in calls
    assert ("src/a.rs:run()", "src/a.rs:helper()") not in calls


def test_self_field_calls_require_unique_local_type_and_method(tmp_path):
    calls = _scoped_calls(tmp_path, {
        "src/a.rs": """
struct Host; struct Other; struct Chain { host: Host, unknown: Missing }
impl Host { fn authorize(&self) {} }
impl Other { fn missing(&self) {} }
impl Chain {
    fn authorize(&self) {}
    fn run(&self) { self.host.authorize(); self.authorize(); self.unknown.missing(); }
}
""",
    })
    assert ("src/a.rs:.run()", "src/a.rs:.authorize()") in calls
    # Both authorize nodes have the same label: inspect actual target identity below.
    result = extract([tmp_path / "src/a.rs"], root=tmp_path, cache_root=tmp_path / "other")
    nodes = {n["id"]: n for n in result["nodes"]}
    targets = [nodes[e["target"]]["source_location"] for e in result["edges"]
               if e["relation"] == "calls" and nodes[e["source"]]["label"] == ".run()"]
    assert sorted(targets) == ["L3", "L6"]


def test_self_field_ambiguous_method_does_not_resolve(tmp_path):
    calls = _scoped_calls(tmp_path, {"src/a.rs": """
struct Host; struct Chain { host: Host }
impl Host { fn act(&self) {} }
impl Host { fn act(&self) {} }
impl Chain { fn run(&self) { self.host.act(); } }
"""})
    assert not any(src.endswith(".run()") for src, _ in calls)


def test_associated_type_binding_skips_lhs_preserves_rhs_and_ordinary_output(tmp_path):
    path = _write(tmp_path / "src/a.rs", """
struct Output; struct Payload; struct Wrapper<T>(T);
fn binding(x: impl Future<Output = Wrapper<Payload>>) {}
fn ordinary(x: Output) {}
""")
    result = extract([path], root=tmp_path, cache_root=tmp_path / "cache")
    nodes = {n["id"]: n["label"] for n in result["nodes"]}
    refs = {(nodes[e["source"]], nodes[e["target"]]) for e in result["edges"]
            if e["relation"] == "references"}
    assert ("binding()", "Output") not in refs
    assert ("binding()", "Wrapper") in refs
    assert ("binding()", "Payload") in refs
    assert ("ordinary()", "Output") in refs


def test_generic_field_type_does_not_bind_to_homonymous_struct(tmp_path):
    calls = _scoped_calls(tmp_path, {"src/a.rs": """
struct T;
impl T { fn authorize(&self) {} }
trait Host { fn authorize(&self); }
struct Chain<T: Host> { host: T }
impl<T: Host> Chain<T> { fn invoke(&self) { self.host.authorize(); } }
struct Concrete { host: T }
impl Concrete { fn invoke_concrete(&self) { self.host.authorize(); } }
"""})
    assert not any(src.endswith(".invoke()") for src, _ in calls)
    assert ("src/a.rs:.invoke_concrete()", "src/a.rs:.authorize()") in calls


def test_tuple_arc_and_lifetime_reference_resolve_local_methods(tmp_path):
    calls = _scoped_calls(tmp_path, {"src/a.rs": """
use std::sync::{Arc, Mutex};
struct State; impl State { fn emit(&self) {} }
struct Subscriber(Arc<State>);
impl Subscriber { fn run(&self) { self.0.emit(); } }
struct Owner; impl Owner { fn lock(&self) {} }
struct Child<'a> { owner: &'a Owner }
impl Child<'_> { fn drop(&self) { self.owner.lock(); } }
"""})
    assert ("src/a.rs:.run()", "src/a.rs:.emit()") in calls
    assert ("src/a.rs:.drop()", "src/a.rs:.lock()") in calls


def test_tuple_wrapper_and_arc_ambiguity_fail_closed(tmp_path):
    calls = _scoped_calls(tmp_path, {"src/a.rs": """
use std::sync::Arc;
use other::Arc;
struct State; impl State { fn emit(&self) {} }
struct Unknown<T>(T);
struct Subscriber(Arc<State>, Unknown<State>);
impl Subscriber { fn run(&self) { self.0.emit(); self.1.emit(); } }
"""})
    assert not any(src.endswith(".run()") for src, _ in calls)


def test_tuple_generic_and_ambiguous_method_fail_closed(tmp_path):
    calls = _scoped_calls(tmp_path, {"src/a.rs": """
use std::sync::Arc;
struct T; impl T { fn act(&self) {} }
struct Generic<T>(Arc<T>);
impl<T> Generic<T> { fn generic(&self) { self.0.act(); } }
struct Host; impl Host { fn work(&self) {} } impl Host { fn work(&self) {} }
struct Concrete(Arc<Host>);
impl Concrete { fn ambiguous(&self) { self.0.work(); } }
"""})
    assert not any(src.endswith((".generic()", ".ambiguous()")) for src, _ in calls)
