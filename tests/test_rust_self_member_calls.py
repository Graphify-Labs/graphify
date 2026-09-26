"""Rust cross-file `self.method()` resolution (#2234).

The shared cross-file call pass drops every member call (a bare method name
like ``log`` has no import evidence and collides with any top-level function
named ``log`` in the corpus, #543/#1219). Every other member-call-heavy
language has a dedicated recovery pass behind that guard; Rust had none, so
`self.apply_block()` never produced a `calls` edge unless the caller and the
method happened to live in the same file.

`self.method()` inside `impl Foo { .. }` types the receiver as `Foo`
syntactically, no inference needed -- these tests exercise that resolution,
including the case Rust makes routine: an `impl Foo` block split across many
files, each minting its own graph node for `Foo`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.extract import extract
from graphify.extractors.rust import extract_rust


def _calls(tmp_path: Path, files: dict[str, str]):
    paths = []
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    result = extract(paths, cache_root=tmp_path / "graphify-out")
    calls = {
        (edge["source"], edge["target"]): edge
        for edge in result["edges"]
        if edge.get("relation") == "calls"
    }
    return calls, result


def _find(result: dict, label: str, id_contains: str) -> str:
    return next(
        node["id"]
        for node in result["nodes"]
        if node.get("label") == label and id_contains in node["id"]
    )


def test_self_call_resolves_across_files_to_a_split_impl_block(tmp_path: Path):
    """The issue's own shape: `impl Foo` split across two files, a `self.`
    call in one block reaching a method defined in the other."""
    calls, result = _calls(tmp_path, {
        "state.rs": (
            "pub struct BlockchainState { height: u64 }\n"
        ),
        "apply.rs": (
            "use crate::state::BlockchainState;\n"
            "impl BlockchainState {\n"
            "    pub fn apply_block(&self) -> u64 { self.height }\n"
            "}\n"
        ),
        "rollback.rs": (
            "use crate::state::BlockchainState;\n"
            "impl BlockchainState {\n"
            "    pub fn rollback_one_block(&self) -> u64 { self.apply_block() }\n"
            "}\n"
        ),
    })
    caller = _find(result, ".rollback_one_block()", "rollback")
    callee = _find(result, ".apply_block()", "apply")
    assert (caller, callee) in calls
    assert calls[(caller, callee)]["confidence"] == "EXTRACTED"


def test_self_call_same_file_control_is_unaffected(tmp_path: Path):
    """Negative control: the pre-existing same-file bare-name resolution
    (which never needed this pass) must keep working exactly as before."""
    calls, result = _calls(tmp_path, {
        "lib.rs": (
            "struct Widget { n: u32 }\n"
            "impl Widget {\n"
            "    fn get(&self) -> u32 { self.n }\n"
            "    fn show(&self) -> u32 { self.get() }\n"
            "}\n"
        ),
    })
    caller = _find(result, ".show()", "widget")
    callee = _find(result, ".get()", "widget")
    assert (caller, callee) in calls


def test_generic_self_call_resolves_across_alpha_renamed_impls(tmp_path: Path):
    """Parameter spelling must not split one simple generic impl family."""
    calls, result = _calls(tmp_path, {
        "state.rs": "pub struct Bucket<T> { value: T }\n",
        "read.rs": (
            "use crate::state::Bucket;\n"
            "impl<T> Bucket<T> {\n"
            "    pub fn fetch_value(&self) {}\n"
            "}\n"
        ),
        "run.rs": (
            "use crate::state::Bucket;\n"
            "impl<U> Bucket<U> {\n"
            "    pub fn run(&self) { self.fetch_value(); }\n"
            "}\n"
        ),
    })
    caller = _find(result, ".run()", "run_bucket_u")
    callee = _find(result, ".fetch_value()", "read_bucket_t")
    assert (caller, callee) in calls
    assert calls[(caller, callee)]["confidence"] == "EXTRACTED"


def test_generic_self_call_does_not_cross_unrelated_same_named_families(
    tmp_path: Path,
):
    """The marker is not proof when two declarations share owner and arity."""
    calls, result = _calls(tmp_path, {
        "a/state.rs": "pub struct Bucket<T> { value: T }\n",
        "a/read.rs": (
            "impl<T> Bucket<T> {\n"
            "    pub fn fetch_value(&self) {}\n"
            "}\n"
        ),
        "b/state.rs": "pub struct Bucket<T> { value: T }\n",
        "b/run.rs": (
            "impl<U> Bucket<U> {\n"
            "    pub fn run(&self) { self.fetch_value(); }\n"
            "}\n"
        ),
    })
    caller = _find(result, ".run()", "b_run_bucket_u")
    assert not {target for (source, target) in calls if source == caller}


def test_generic_self_call_without_a_declaration_fails_closed(tmp_path: Path):
    """Impl blocks alone do not prove that same-named owners are one family."""
    calls, result = _calls(tmp_path, {
        "method.rs": (
            "impl<T> Bucket<T> { pub fn fetch_value(&self) {} }\n"
        ),
        "caller.rs": (
            "impl<U> Bucket<U> {\n"
            "    pub fn run(&self) { self.fetch_value(); }\n"
            "}\n"
        ),
    })
    caller = _find(result, ".run()", "caller_bucket_u")
    assert not {target for (source, target) in calls if source == caller}


def test_generic_self_call_counts_collapsed_same_file_declarations(
    tmp_path: Path,
):
    """Nested modules must not hide two unrelated declarations behind one ID."""
    calls, result = _calls(tmp_path, {
        "state.rs": (
            "pub mod a { pub struct Bucket<T>(pub T); }\n"
            "pub mod b { pub struct Bucket<T>(pub T); }\n"
        ),
        "a_impl.rs": (
            "impl<T> Bucket<T> {\n"
            "    pub fn fetch_value(&self) {}\n"
            "}\n"
        ),
        "fallback.rs": (
            "pub trait Fallback { fn fetch_value(&self) {} }\n"
        ),
        "b_impl.rs": (
            "impl<T> Fallback for Bucket<T> {}\n"
            "impl<U> Bucket<U> {\n"
            "    pub fn run(&self) { self.fetch_value(); }\n"
            "}\n"
        ),
    })
    caller = _find(result, ".run()", "b_impl_bucket_u")
    assert not {target for (source, target) in calls if source == caller}


@pytest.mark.parametrize(
    ("declaration", "callee_impl", "caller_impl"),
    [
        (
            "pub struct Bucket<T> { value: T }\n",
            "impl<T: Clone> Bucket<T>",
            "impl<U: Clone> Bucket<U>",
        ),
        (
            "pub struct Bucket<T> { value: T }\n",
            "impl<T> Bucket<T> where T: Clone",
            "impl<U> Bucket<U> where U: Clone",
        ),
        (
            (
                "pub struct Bucket<T> { value: T }\n"
                "trait Fetch { fn fetch_value(&self); }\n"
            ),
            "impl<T> Fetch for Bucket<T>",
            "impl<U> Bucket<U>",
        ),
        (
            "pub struct Bucket<'a, T> { value: &'a T }\n",
            "impl<'a, T> Bucket<'a, T>",
            "impl<'b, U> Bucket<'b, U>",
        ),
        (
            "pub struct Bucket<const N: usize> { value: [u8; N] }\n",
            "impl<const N: usize> Bucket<N>",
            "impl<const M: usize> Bucket<M>",
        ),
        (
            "pub struct Bucket<T> { value: T }\n",
            "impl<T> Bucket<Vec<T>>",
            "impl<U> Bucket<U>",
        ),
        (
            "pub struct Bucket<T> { value: T }\n",
            "impl Bucket<String>",
            "impl<U> Bucket<U>",
        ),
        (
            "pub struct Pair<T, U> { left: T, right: U }\n",
            "impl<T> Pair<T, T>",
            "impl<X, Y> Pair<X, Y>",
        ),
        (
            "pub struct Pair<T, U> { left: T, right: U }\n",
            "impl<T, U> Pair<U, T>",
            "impl<X, Y> Pair<X, Y>",
        ),
    ],
    ids=[
        "bounded", "where", "trait", "lifetime", "const", "nested",
        "concrete", "repeated", "permuted",
    ],
)
def test_unsupported_generic_impl_shapes_fail_closed(
    tmp_path: Path,
    declaration: str,
    callee_impl: str,
    caller_impl: str,
):
    """Unsupported type semantics get neither a marker nor a guessed edge."""
    method = tmp_path / "method.rs"
    method.write_text(
        f"{callee_impl} {{\n    pub fn fetch_value(&self) {{}}\n}}\n",
        encoding="utf-8",
    )
    impl_nodes = [
        node for node in extract_rust(method)["nodes"]
        if node.get("label", "").startswith(("Bucket", "Pair"))
    ]
    assert impl_nodes
    assert all("_rust_impl_key" not in node for node in impl_nodes)

    calls, result = _calls(tmp_path / "corpus", {
        "state.rs": declaration,
        "method.rs": f"{callee_impl} {{\n    pub fn fetch_value(&self) {{}}\n}}\n",
        "caller.rs": (
            f"{caller_impl} {{\n"
            "    pub fn run(&self) { self.fetch_value(); }\n"
            "}\n"
        ),
    })
    caller = _find(result, ".run()", "caller")
    assert not {target for (source, target) in calls if source == caller}


@pytest.mark.parametrize("deferred_first", [False, True])
def test_mixed_simple_and_bounded_impl_blocks_fail_closed(
    tmp_path: Path,
    deferred_first: bool,
):
    """A shared impl node cannot lend eligibility to a bounded block."""
    simple_target = "impl<T> Bucket<T> { fn marker_a(&self) {} }\n"
    bounded_target = (
        "impl<T: Clone> Bucket<T> { pub fn fetch_value(&self) {} }\n"
    )
    simple_caller = "impl<U> Bucket<U> { fn marker_b(&self) {} }\n"
    bounded_caller = (
        "impl<U: Clone> Bucket<U> {\n"
        "    pub fn run(&self) { self.fetch_value(); }\n"
        "}\n"
    )
    def order(simple: str, deferred: str) -> str:
        return deferred + simple if deferred_first else simple + deferred
    calls, result = _calls(tmp_path, {
        "state.rs": "pub struct Bucket<T> { value: T }\n",
        "target.rs": order(simple_target, bounded_target),
        "caller.rs": order(simple_caller, bounded_caller),
    })
    caller = _find(result, ".run()", "caller_bucket_u")
    assert not {target for (source, target) in calls if source == caller}

    target_impl = next(
        node for node in extract_rust(tmp_path / "target.rs")["nodes"]
        if node.get("label") == "Bucket<T>"
    )
    assert "_rust_impl_key" not in target_impl
    raw_call = next(
        call for call in extract_rust(tmp_path / "caller.rs")["raw_calls"]
        if call.get("callee") == "fetch_value"
    )
    assert "rust_self_impl_key" not in raw_call


def test_mixed_simple_and_trait_impl_target_fails_closed(tmp_path: Path):
    """A coalesced trait impl must not expose its methods as inherent ones."""
    calls, result = _calls(tmp_path, {
        "state.rs": "pub struct Bucket<T> { value: T }\n",
        "target.rs": (
            "pub trait Fetch { fn fetch_value(&self); }\n"
            "impl<T> Bucket<T> { fn marker(&self) {} }\n"
            "impl<T> Fetch for Bucket<T> {\n"
            "    fn fetch_value(&self) {}\n"
            "}\n"
        ),
        "caller.rs": (
            "impl<U> Bucket<U> {\n"
            "    pub fn run(&self) { self.fetch_value(); }\n"
            "}\n"
        ),
    })
    caller = _find(result, ".run()", "caller_bucket_u")
    assert not {target for (source, target) in calls if source == caller}
    target_impl = next(
        node for node in extract_rust(tmp_path / "target.rs")["nodes"]
        if node.get("label") == "Bucket<T>"
    )
    assert "_rust_impl_key" not in target_impl


def test_scoped_self_call_remains_deferred_across_impl_files(tmp_path: Path):
    """`Self::method()` is a scoped-call form, outside this resolver slice."""
    calls, result = _calls(tmp_path, {
        "state.rs": "pub struct Bucket<T> { value: T }\n",
        "method.rs": (
            "impl<T> Bucket<T> {\n"
            "    pub fn fetch_value(&self) {}\n"
            "}\n"
        ),
        "caller.rs": (
            "impl<U> Bucket<U> {\n"
            "    pub fn run(&self) { Self::fetch_value(self); }\n"
            "}\n"
        ),
    })
    caller = _find(result, ".run()", "caller")
    assert not {target for (source, target) in calls if source == caller}


def test_generic_self_call_invalidates_markerless_ast_cache(
    tmp_path: Path,
    monkeypatch,
):
    """A same-version cache from before the marker contract must be missed."""
    import graphify.cache as cache_mod
    from graphify.cache import save_cached

    files = {
        "state.rs": "pub struct Bucket<T> { value: T }\n",
        "method.rs": (
            "impl<T> Bucket<T> {\n"
            "    pub fn fetch_value(&self) {}\n"
            "}\n"
        ),
        "caller.rs": (
            "impl<U> Bucket<U> {\n"
            "    pub fn run(&self) { self.fetch_value(); }\n"
            "}\n"
        ),
    }
    paths = []
    current_schema = cache_mod._AST_CACHE_SCHEMA
    assert current_schema >= 4
    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", current_schema - 1)
    monkeypatch.setattr(cache_mod, "_cleaned_ast_dirs", set())
    for name, body in files.items():
        path = tmp_path / name
        path.write_text(body, encoding="utf-8")
        paths.append(path)
        stale = extract_rust(path)
        for node in stale["nodes"]:
            node.pop("_rust_impl_key", None)
        for raw_call in stale.get("raw_calls", []):
            raw_call.pop("rust_self_impl_key", None)
        save_cached(
            path,
            stale,
            root=tmp_path,
            cache_root=tmp_path,
            kind="ast",
        )

    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", current_schema)
    monkeypatch.setattr(cache_mod, "_cleaned_ast_dirs", set())
    result = extract(paths, root=tmp_path, cache_root=tmp_path)
    caller = _find(result, ".run()", "caller_bucket_u")
    callee = _find(result, ".fetch_value()", "method_bucket_t")
    assert any(
        edge.get("relation") == "calls"
        and edge.get("source") == caller
        and edge.get("target") == callee
        for edge in result["edges"]
    )


def test_self_call_to_ambiguous_type_name_yields_no_edge(tmp_path: Path):
    """Two DIFFERENT structs across the corpus happen to share the bare name
    `Config`, and both define a same-named method -- the exactly-one-candidate
    guard must refuse to pick either."""
    calls, result = _calls(tmp_path, {
        "a.rs": (
            "struct Config { x: i32 }\n"
            "impl Config {\n"
            "    fn load(&self) -> i32 { self.x }\n"
            "}\n"
        ),
        "b.rs": (
            "struct Config { y: i32 }\n"
            "impl Config {\n"
            "    fn load(&self) -> i32 { self.y }\n"
            "}\n"
        ),
        "c.rs": (
            "struct Config { z: i32 }\n"
            "impl Config {\n"
            "    fn start(&self) -> i32 { self.load() }\n"
            "}\n"
        ),
    })
    caller = _find(result, ".start()", "c_config")
    targets = {tgt for (src, tgt) in calls if src == caller}
    assert not targets, "`Config::load` is ambiguous across a.rs/b.rs -- must not guess"


def test_self_call_to_undefined_method_yields_no_edge(tmp_path: Path):
    """A `self.` call whose method genuinely doesn't exist anywhere in the
    corpus must not fabricate a target."""
    calls, result = _calls(tmp_path, {
        "lib.rs": (
            "struct Widget { n: u32 }\n"
            "impl Widget {\n"
            "    fn show(&self) -> u32 { self.missing() }\n"
            "}\n"
        ),
    })
    caller = _find(result, ".show()", "widget")
    targets = {tgt for (src, tgt) in calls if src == caller}
    assert not targets


def test_resolver_is_not_suppressed_by_an_unrelated_edge_to_the_same_pair(tmp_path: Path):
    """A caller that already has a DIFFERENT relation to the exact same
    target (e.g. a references edge from also naming the type elsewhere)
    must still get its calls edge -- the two relations are not mutually
    exclusive, and an existing non-calls edge says nothing about whether a
    call was resolved."""
    from graphify.extract import _resolve_rust_self_member_calls

    all_nodes = [
        {"id": "impl_foo", "label": "Foo", "source_file": "a.rs"},
        {"id": "impl_foo_method", "label": ".method()", "source_file": "a.rs"},
        {"id": "impl_foo_caller", "label": ".caller()", "source_file": "a.rs"},
    ]
    all_edges = [
        {"source": "impl_foo", "target": "impl_foo_method", "relation": "method"},
        # A pre-existing, unrelated edge between the exact same pair the
        # resolver is about to consider -- must not suppress the new one.
        {"source": "impl_foo_caller", "target": "impl_foo_method", "relation": "references"},
    ]
    per_file = [{
        "raw_calls": [{
            "caller_nid": "impl_foo_caller",
            "callee": "method",
            "rust_self_type": "Foo",
            "source_file": "a.rs",
            "source_location": "L1",
        }],
    }]

    _resolve_rust_self_member_calls(per_file, all_nodes, all_edges)

    calls = {
        (e["source"], e["target"])
        for e in all_edges
        if e["relation"] == "calls"
    }
    assert ("impl_foo_caller", "impl_foo_method") in calls


def test_resolver_treats_a_duplicate_method_index_key_as_ambiguous(tmp_path: Path):
    """Two DIFFERENT method nodes sharing both a source impl node and a
    stripped label must surface as an ambiguity (no edge), not silently
    keep whichever one a plain dict overwrite happened to see last."""
    from graphify.extract import _resolve_rust_self_member_calls

    all_nodes = [
        {"id": "impl_foo", "label": "Foo", "source_file": "a.rs"},
        {"id": "impl_foo_method_a", "label": ".method()", "source_file": "a.rs"},
        {"id": "impl_foo_method_b", "label": ".method()", "source_file": "a.rs"},
        {"id": "impl_foo_caller", "label": ".caller()", "source_file": "a.rs"},
    ]
    all_edges = [
        {"source": "impl_foo", "target": "impl_foo_method_a", "relation": "method"},
        {"source": "impl_foo", "target": "impl_foo_method_b", "relation": "method"},
    ]
    per_file = [{
        "raw_calls": [{
            "caller_nid": "impl_foo_caller",
            "callee": "method",
            "rust_self_type": "Foo",
            "source_file": "a.rs",
            "source_location": "L1",
        }],
    }]

    _resolve_rust_self_member_calls(per_file, all_nodes, all_edges)

    calls = {
        (e["source"], e["target"])
        for e in all_edges
        if e["relation"] == "calls"
    }
    assert not calls, "two same-labeled method nodes on one type must not guess"


def test_self_call_does_not_link_across_two_unrelated_types_sharing_a_name(tmp_path: Path):
    """Two UNRELATED structs happen to share the bare name `Config`; each
    defines a DIFFERENT method (no name collision between them). Pooling
    methods across every same-labeled node -- the mechanism that makes a
    split impl block work -- must not also link a caller in one type's impl
    to a method that only exists on the other, unrelated type. This is the
    shape a shared trait default (present in real, compiling Rust: one type
    overrides a trait method, the other relies on the default and so never
    gets an explicit method node for it) would trigger."""
    calls, result = _calls(tmp_path, {
        "a.rs": (
            "struct Config { x: i32 }\n"
            "impl Config {\n"
            "    fn foo(&self) -> i32 { self.x }\n"
            "}\n"
        ),
        "b.rs": (
            "struct Config { y: i32 }\n"
            "impl Config {\n"
            "    fn bar(&self) -> i32 { self.y }\n"
            "    fn start(&self) -> i32 { self.foo() }\n"
            "}\n"
        ),
    })
    caller = _find(result, ".start()", "b_config")
    targets = {tgt for (src, tgt) in calls if src == caller}
    assert not targets, \
        "`Config` is declared twice (a.rs, b.rs) -- must not link to the other one's foo()"
