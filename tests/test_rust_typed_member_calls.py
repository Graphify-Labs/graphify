"""Rust `x.m()` / `self.field.m()` resolved through the receiver's type.

`_resolve_rust_self_member_calls` handles `self.m()` and leaves a non-self
receiver "for a future extension". rust.py now records how each receiver's type
is found (a typed parameter or `let`, a struct field, the return type of
`T::f()` / `f()` / `x.m()`, unwrapped by `?` or `.unwrap()`), and
`_resolve_rust_typed_member_calls` evaluates it over the corpus. A receiver it
cannot type gets no edge rather than a bare-name guess.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract

_MATCHER = (
    "pub struct Matcher;\n"
    "impl Matcher {\n"
    "    pub fn new() -> Self { Matcher }\n"
    "    pub fn open() -> std::io::Result<Matcher> { Ok(Matcher) }\n"
    "    pub fn find(&self) -> usize { 0 }\n"
    "}\n"
)


def _calls(tmp_path: Path, files: dict[str, str]) -> set[tuple[str, str, str]]:
    paths = []
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        paths.append(p)
    r = extract(paths, root=tmp_path, cache_root=tmp_path / "graphify-out")
    nodes = {n["id"]: n for n in r["nodes"]}
    return {
        (nodes[e["source"]]["label"], nodes[e["target"]]["label"],
         Path(str(nodes[e["target"]].get("source_file", ""))).as_posix())
        for e in r["edges"]
        if e["relation"] == "calls" and e["source"] in nodes and e["target"] in nodes
    }


def _hit(calls, caller: str, callee: str, in_file: str) -> bool:
    return any(s == caller and t == callee and f.endswith(in_file) for s, t, f in calls)


def test_receiver_typed_by_parameter_let_and_constructor(tmp_path: Path):
    calls = _calls(tmp_path, {
        "src/matcher.rs": _MATCHER,
        "src/search.rs": (
            "use crate::matcher::Matcher;\n"
            "pub fn by_param(m: &Matcher) -> usize { m.find() }\n"
            "pub fn by_let() -> usize { let m: Matcher = Matcher::new(); m.find() }\n"
            "pub fn by_new() -> usize { let m = Matcher::new(); m.find() }\n"
            "pub fn by_try() -> std::io::Result<usize> { let m = Matcher::open()?; Ok(m.find()) }\n"
            "pub fn by_chain() -> usize { Matcher::new().find() }\n"
        ),
    })
    for caller in ("by_param()", "by_let()", "by_new()", "by_try()", "by_chain()"):
        assert _hit(calls, caller, ".find()", "src/matcher.rs"), (caller, calls)


def test_receiver_typed_by_struct_field_and_free_fn_return(tmp_path: Path):
    calls = _calls(tmp_path, {
        "src/matcher.rs": _MATCHER,
        "src/worker.rs": (
            "use crate::matcher::Matcher;\n"
            "pub fn make() -> Matcher { Matcher::new() }\n"
            "pub struct Worker { matcher: std::sync::Arc<Matcher> }\n"
            "impl Worker {\n"
            "    pub fn run(&self) -> usize { self.matcher.find() }\n"
            "}\n"
            "pub fn direct() -> usize { let m = make(); m.find() }\n"
        ),
    })
    assert _hit(calls, ".run()", ".find()", "src/matcher.rs"), calls
    assert _hit(calls, "direct()", ".find()", "src/matcher.rs"), calls


def test_type_from_another_crate_or_std_path_gets_no_edge(tmp_path: Path):
    # `fs::DirEntry` is std's, not the crate's own `DirEntry`.
    calls = _calls(tmp_path, {
        "src/walk.rs": (
            "use std::fs;\n"
            "pub struct DirEntry;\n"
            "impl DirEntry { pub fn metadata(&self) -> u8 { 0 } }\n"
            "pub fn stat(ent: &fs::DirEntry) { let _ = ent.metadata(); }\n"
            "pub fn own(ent: &crate::walk::DirEntry) -> u8 { ent.metadata() }\n"
        ),
    })
    assert not _hit(calls, "stat()", ".metadata()", "src/walk.rs"), calls
    assert _hit(calls, "own()", ".metadata()", "src/walk.rs"), calls


def test_untyped_closure_parameter_hides_the_outer_binding(tmp_path: Path):
    calls = _calls(tmp_path, {
        "src/matcher.rs": _MATCHER,
        "src/each.rs": (
            "use crate::matcher::Matcher;\n"
            "pub fn each(m: &Matcher, items: &[u8]) -> usize {\n"
            "    items.iter().map(|m| m.find()).count()\n"
            "}\n"
        ),
    })
    assert not _hit(calls, "each()", ".find()", "src/matcher.rs"), calls


def test_same_type_name_in_two_crates_picks_the_callers_crate(tmp_path: Path):
    config = "pub struct Config;\nimpl Config {{ pub fn {m}(&self) -> u8 {{ 0 }} }}\n"
    calls = _calls(tmp_path, {
        "crates/a/src/config.rs": config.format(m="load"),
        "crates/b/src/config.rs": config.format(m="load"),
        "crates/a/src/main.rs": "use crate::config::Config;\npub fn go(c: &Config) -> u8 { c.load() }\n",
    })
    assert _hit(calls, "go()", ".load()", "crates/a/src/config.rs"), calls
    assert not _hit(calls, "go()", ".load()", "crates/b/src/config.rs"), calls


def test_untyped_receiver_gets_no_bare_name_edge(tmp_path: Path):
    # `v.find()` on a value of unknown type used to bind to the file's own
    # `Matcher::find` by name.
    calls = _calls(tmp_path, {
        "src/lib.rs": _MATCHER + "pub fn scan(v: Vec<u8>) -> usize { v.iter().count() + v.find() }\n",
    })
    assert not _hit(calls, "scan()", ".find()", "src/lib.rs"), calls


def test_self_call_in_a_trait_default_method_still_binds(tmp_path: Path):
    calls = _calls(tmp_path, {
        "src/lib.rs": (
            "pub trait Sink {\n"
            "    fn begin(&self) -> u8 { self.flush() }\n"
            "    fn flush(&self) -> u8 { 0 }\n"
            "}\n"
        ),
    })
    assert _hit(calls, ".begin()", ".flush()", "src/lib.rs"), calls


def test_schema_bump_retires_entries_cached_without_receiver_types(tmp_path: Path, monkeypatch):
    """A schema-7 entry has no `rust_receiver` / `_rust_ret`: replaying it would
    leave `m.find()` with no edge."""
    import graphify.cache as cache_mod
    from graphify.cache import save_cached
    from graphify.extractors.rust import extract_rust

    files = {
        "src/matcher.rs": _MATCHER,
        "src/search.rs": "use crate::matcher::Matcher;\npub fn go() -> usize { let m = Matcher::new(); m.find() }\n",
    }
    paths = []
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        paths.append(p)
    current_schema = cache_mod._AST_CACHE_SCHEMA
    monkeypatch.setattr(cache_mod, "_EXTRACTOR_VERSION", "same-version")
    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", 7)  # last schema without the facts
    monkeypatch.setattr(cache_mod, "_cleaned_ast_dirs", set())
    for p in paths:
        stale = extract_rust(p)
        for rc in stale.get("raw_calls", []):
            rc.pop("rust_receiver", None)
        for node in stale["nodes"]:
            for key in ("_rust_ret", "_rust_ret_ok", "_rust_fields"):
                node.pop(key, None)
        save_cached(p, stale, root=tmp_path, cache_root=tmp_path, kind="ast")

    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", current_schema)
    monkeypatch.setattr(cache_mod, "_cleaned_ast_dirs", set())
    r = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    nodes = {n["id"]: n for n in r["nodes"]}
    assert any(
        e["relation"] == "calls" and nodes[e["source"]]["label"] == "go()" and nodes[e["target"]]["label"] == ".find()"
        for e in r["edges"]
    )


def test_for_and_if_let_values_still_read_the_outer_binding(tmp_path: Path):
    # The new `m` of `if let Some(m) = m.first()` / `for m in m.entries()` only exists
    # after its value; the value's `m` is still the typed parameter.
    calls = _calls(tmp_path, {
        "src/matcher.rs": (
            "pub struct Matcher;\n"
            "impl Matcher {\n"
            "    pub fn first(&self) -> Option<u8> { None }\n"
            "    pub fn entries(&self) -> Vec<u8> { Vec::new() }\n"
            "}\n"
        ),
        "src/use_it.rs": (
            "use crate::matcher::Matcher;\n"
            "pub fn pick(m: &Matcher) -> u8 { if let Some(m) = m.first() { m } else { 0 } }\n"
            "pub fn each(m: &Matcher) -> usize { let mut n = 0; for m in m.entries() { n += m as usize; } n }\n"
        ),
    })
    assert _hit(calls, "pick()", ".first()", "src/matcher.rs"), calls
    assert _hit(calls, "each()", ".entries()", "src/matcher.rs"), calls


def test_crate_is_the_deepest_root_above_the_file(tmp_path: Path):
    # A `tests` module inside `src/`, and a checkout that itself sits under a
    # folder named `src`, both keep the caller in its own crate.
    config = "pub struct Config;\nimpl Config {{ pub fn {m}(&self) -> u8 {{ 0 }} }}\n"
    root = tmp_path / "src" / "work"
    calls = _calls(root, {
        "crates/a/src/config.rs": config.format(m="load"),
        "crates/b/src/config.rs": config.format(m="load"),
        "crates/a/src/tests/check.rs": "use crate::config::Config;\npub fn unit(c: &Config) -> u8 { c.load() }\n",
        "crates/a/tests/it.rs": "use a::config::Config;\npub fn integration(c: &Config) -> u8 { c.load() }\n",
    })
    for caller in ("unit()", "integration()"):
        assert _hit(calls, caller, ".load()", "crates/a/src/config.rs"), (caller, calls)
        assert not _hit(calls, caller, ".load()", "crates/b/src/config.rs"), (caller, calls)
