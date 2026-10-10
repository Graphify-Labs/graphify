"""Member-level protocol dispatch for Swift.

`store.fetch()` on an injected `Store` resolves to the protocol's own `.fetch()`
requirement (#3673), because that is what the call site names. The conforming
`RemoteStore.fetch()` is a separate node, and nothing joins the two, so a
directed walk stops at the protocol and every chain through an injected
dependency is cut at that point — the Swift twin of the C# gap #3003 closed.

The mechanism — single-conformer, single-owner, per-method `dispatches_to`
edges at INFERRED — lives in `graphify.interface_dispatch` and is shared with
the C# pass; this module fixes the Swift gate. Both ends of a pair must be
declared in a `.swift` file: `implements` is resolved by name, so a Kotlin or
Java class declaring the same supertype name binds to the Swift protocol when
that is the only node with the name, and linking a requirement to its method
would be a wrong edge rather than a missing one. An Objective-C class adopting
a Swift protocol across the bridge is a real thing, but claiming it needs the
ObjC extractor's own evidence.

What the Swift extractor hands this pass:

- Conformance arrives as `implements` from struct/enum/actor declarations, from
  a class whose protocol is declared in the same file, and from
  `extension T: P`, which `_merge_swift_extensions` folds into T before the
  registry runs. A `class C: P` whose protocol lives in another file is
  classified `inherits` — Swift spells a superclass and a protocol the same way
  and the per-file classifier cannot see P — so it is not dispatched here.
- A default implementation in a protocol extension is folded into the
  protocol's own node, so a conformer that does not override it owns no
  candidate and gets no edge: the call really does land on the default.
- Builtin protocols (`View`, `Codable`, …) are sourceless stubs and never pass
  the declared-in guard.
"""
from __future__ import annotations

from graphify.interface_dispatch import resolve_interface_dispatch

_SWIFT_SUFFIXES = (".swift",)


def resolve_swift_protocol_dispatch(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Link each single-conformer Swift protocol requirement to its implementation."""
    resolve_interface_dispatch(per_file, all_nodes, all_edges, suffixes=_SWIFT_SUFFIXES)
