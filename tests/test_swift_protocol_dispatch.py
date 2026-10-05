"""Swift member-level protocol dispatch.

`repo.fetch()` on an injected `Repository` resolves to the protocol's own
`.fetch()` requirement (#3673), which is what the call site names. The
conformer's `.fetch()` is a separate node with nothing joining the two, so a
directed walk stops at the protocol and every chain through an injected
dependency is cut there — the Swift twin of the C# gap #3003 closed.

`resolve_swift_protocol_dispatch` links the requirement to the implementing
method when the protocol has exactly one conformer and that conformer owns
exactly one method of the same name. Ambiguity at either step leaves the pair
alone, the same single-owner guard the C#, Pascal and Ruby resolvers use.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files], cache_root=Path(tempfile.mkdtemp()))
    finally:
        os.chdir(old)
    dispatch = {(e["source"], e["target"]) for e in r["edges"]
                if e["relation"] == "dispatches_to"}
    return dispatch, r


def _find(r, label, id_contains):
    return next(n["id"] for n in r["nodes"]
                if n["label"] == label and id_contains in n["id"])


def _reachable(r, start: str) -> set[str]:
    adjacency: dict[str, list[str]] = {}
    for e in r["edges"]:
        adjacency.setdefault(e["source"], []).append(e["target"])
    seen = {start}
    queue = [start]
    while queue:
        for nxt in adjacency.get(queue.pop(0), []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


# Protocol in one file, conformer in another, consumer injected with the
# protocol: the shape every service layer in an iOS app has.
_INJECTED = {
    "Core/Store.swift": (
        "protocol Store {\n"
        "    func fetch() async throws -> [Item]\n"
        "}\n"
        "struct Item { let id: Int }\n"
    ),
    "Services/RemoteStore.swift": (
        "struct RemoteStore: Store {\n"
        "    func fetch() async throws -> [Item] { try decode() }\n"
        "    func decode() throws -> [Item] { [] }\n"
        "}\n"
    ),
    "App/ItemModel.swift": (
        "final class ItemModel {\n"
        "    private let store: Store\n"
        "    init(store: Store) { self.store = store }\n"
        "    func load() async throws -> [Item] { try await store.fetch() }\n"
        "}\n"
    ),
}


def test_single_conformer_links_the_protocol_requirement(tmp_path):
    dispatch, r = _extract(tmp_path, _INJECTED)
    assert (_find(r, ".fetch()", "core_store"), _find(r, ".fetch()", "remotestore")) in dispatch


def test_chain_through_an_injected_dependency_becomes_reachable(tmp_path):
    dispatch, r = _extract(tmp_path, _INJECTED)
    assert dispatch
    # load -> Store.fetch -> RemoteStore.fetch -> decode
    assert _find(r, ".decode()", "remotestore") in _reachable(r, _find(r, ".load()", "itemmodel"))


def test_the_call_to_the_protocol_requirement_is_kept(tmp_path):
    # Additive: the call site really does name the protocol.
    _, r = _extract(tmp_path, _INJECTED)
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    assert (_find(r, ".load()", "itemmodel"), _find(r, ".fetch()", "core_store")) in calls


def test_dispatch_edge_shape(tmp_path):
    # INFERRED: the target is forced once there is a single conformer, but the
    # source text never names it. Anchored at the conformer, where the method is.
    _, r = _extract(tmp_path, _INJECTED)
    edge = next(e for e in r["edges"] if e["relation"] == "dispatches_to")
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.85
    assert edge["context"] == "call"
    assert edge["source_file"].endswith("RemoteStore.swift")


def test_conformance_declared_in_an_extension_links(tmp_path):
    # `extension T: P` is the idiomatic place to declare a conformance. The
    # extension is folded into T before the resolvers run, so the pair is the
    # same as a conformance written on the type.
    dispatch, r = _extract(tmp_path, {
        "Core/Store.swift": "protocol Store { func fetch() }\n",
        "Services/RemoteStore.swift": (
            "final class RemoteStore { }\n"
            "extension RemoteStore: Store {\n"
            "    func fetch() { }\n"
            "}\n"
        ),
    })
    assert (_find(r, ".fetch()", "core_store"), _find(r, ".fetch()", "remotestore")) in dispatch


def test_class_conformer_links_when_the_protocol_is_in_the_same_file(tmp_path):
    dispatch, r = _extract(tmp_path, {"S.swift": (
        "protocol Store { func fetch() }\n"
        "final class RemoteStore: Store { func fetch() { } }\n"
    )})
    assert (_find(r, ".fetch()", "s_store"), _find(r, ".fetch()", "remotestore")) in dispatch


def test_class_conformer_of_a_protocol_in_another_file_is_a_known_limit(tmp_path):
    # Swift spells a superclass and a protocol the same way in a class's
    # inheritance list. `_swift_classify_base` only knows the protocols declared
    # in the file it is extracting, so `class C: P` with P elsewhere is emitted
    # as `inherits`, and this pass — keyed on `implements`, like the C# one —
    # never sees it. Teaching the classifier about the corpus is follow-up work;
    # struct/enum/actor conformers and `extension C: P` are unaffected.
    dispatch, r = _extract(tmp_path, {
        "Core/Store.swift": "protocol Store { func fetch() }\n",
        "Services/RemoteStore.swift": "final class RemoteStore: Store { func fetch() { } }\n",
    })
    heritage = {e["relation"] for e in r["edges"]
                if e["source"] == _find(r, "RemoteStore", "remotestore")
                and e["target"] == _find(r, "Store", "core_store")}
    assert heritage == {"inherits"}
    assert not dispatch


def test_two_conformers_produce_no_edge(tmp_path):
    dispatch, _ = _extract(tmp_path, {"S.swift": (
        "protocol Shape { func area() -> Double }\n"
        "struct Square: Shape { func area() -> Double { 1 } }\n"
        "struct Circle: Shape { func area() -> Double { 2 } }\n"
    )})
    assert not dispatch


def test_no_matching_member_produces_no_edge(tmp_path):
    dispatch, _ = _extract(tmp_path, {"S.swift": (
        "protocol Store { func fetch() }\n"
        "struct Local: Store { func other() { } }\n"
    )})
    assert not dispatch


def test_default_implementation_in_a_protocol_extension_is_not_dispatched(tmp_path):
    # `extension P { func m() {} }` is folded into P's own node, so a conformer
    # that does not override `m` owns no candidate — the call really does land
    # on the default, which the graph already reaches through P.m.
    dispatch, _ = _extract(tmp_path, {"S.swift": (
        "protocol Greeter { func greet() }\n"
        "extension Greeter { func greet() { } }\n"
        "struct Silent: Greeter { }\n"
    )})
    assert not dispatch


def test_overriding_a_default_implementation_links(tmp_path):
    dispatch, r = _extract(tmp_path, {"S.swift": (
        "protocol Greeter { func greet() }\n"
        "extension Greeter { func greet() { } }\n"
        "struct Loud: Greeter { func greet() { } }\n"
    )})
    assert (_find(r, ".greet()", "s_greeter"), _find(r, ".greet()", "s_loud")) in dispatch


def test_builtin_protocol_conformance_is_skipped_and_static_requirements_link(tmp_path):
    # `View` is a sourceless stub minted for the dangling reference; it carries
    # no members and never passes the declared-in guard. The user protocol
    # beside it still links, static requirement included.
    dispatch, r = _extract(tmp_path, {"V.swift": (
        "import SwiftUI\n"
        "protocol Factory { static func make() -> Self }\n"
        "struct Box: View, Factory {\n"
        "    var body: some View { Text(\"x\") }\n"
        "    static func make() -> Box { Box() }\n"
        "}\n"
    )})
    assert dispatch == {(_find(r, ".make()", "v_factory"), _find(r, ".make()", "v_box"))}


def test_subclassing_a_class_is_out_of_scope(tmp_path):
    # `class Sub: Base` is an `inherits` edge, and the base method may well be
    # the real target, so walking inheritance is a different bet from dispatch.
    dispatch, _ = _extract(tmp_path, {"S.swift": (
        "class Base { func m() { } }\n"
        "final class Sub: Base { override func m() { } }\n"
    )})
    assert not dispatch


def test_protocol_inheritance_is_not_walked_transitively(tmp_path):
    # Known limit, same as the C# pass: Base's only "conformer" is Child, a
    # protocol that declares nothing, so Base.m never reaches Impl.m.
    dispatch, _ = _extract(tmp_path, {"S.swift": (
        "protocol Base { func m() }\n"
        "protocol Child: Base { }\n"
        "struct Impl: Child { func m() { } }\n"
    )})
    assert not dispatch


def test_a_kotlin_conformer_of_a_same_named_protocol_is_not_dispatched_to(tmp_path):
    # `implements` resolves by name, so in a mixed corpus a Kotlin class
    # declaring `: Store` binds to the Swift protocol when that is the only node
    # with the name. Linking a Swift requirement to a Kotlin method would be a
    # wrong edge rather than a missing one.
    dispatch, _ = _extract(tmp_path, {
        "Store.swift": "protocol Store { func fetch() }\n",
        "RemoteStore.kt": "class RemoteStore : Store { fun fetch() {} }\n",
    })
    assert not dispatch


def test_a_csharp_corpus_is_untouched_by_the_swift_pass(tmp_path):
    # Both ends must be Swift declarations; the C# pair is the C# pass's job.
    from graphify.swift_dispatch import resolve_swift_protocol_dispatch

    nodes = [
        {"id": "iface", "label": "IR", "source_file": "a.cs", "_callable_class": True},
        {"id": "impl", "label": "A", "source_file": "a.cs", "_callable_class": True},
        {"id": "iface_m", "label": ".M()", "source_file": "a.cs", "_callable": True},
        {"id": "impl_m", "label": ".M()", "source_file": "a.cs", "_callable": True},
    ]
    edges = [
        {"source": "impl", "target": "iface", "relation": "implements"},
        {"source": "iface", "target": "iface_m", "relation": "method"},
        {"source": "impl", "target": "impl_m", "relation": "method"},
    ]
    resolve_swift_protocol_dispatch([], nodes, edges)
    assert not any(e["relation"] == "dispatches_to" for e in edges)


def test_swift_pass_is_registered_after_the_csharp_pass():
    import graphify.extract  # noqa: F401  (registers resolvers on import)
    from graphify.resolver_registry import registered_resolvers

    names = [r.name for r in registered_resolvers()]
    assert "swift_protocol_dispatch" in names
    assert names.index("csharp_interface_dispatch") < names.index("swift_protocol_dispatch")
