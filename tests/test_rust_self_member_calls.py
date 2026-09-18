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

from graphify.extract import extract


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
