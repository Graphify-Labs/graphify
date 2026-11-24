"""Member-level interface dispatch for Go.

`d.provider.GetWithDataSource()` where `provider` is a `pluginContextProvider`
resolves to the interface's own `.GetWithDataSource()` requirement, because that
is what the call site names. The concrete `Provider.GetWithDataSource()` is a
separate node, and nothing joins the two, so a directed walk stops at the
interface — the Go twin of the C# gap #3003 closed.

C# and Swift feed `graphify.interface_dispatch` with the `implements` edges
their extractors read off a declaration. Go has no such declaration: a type
implements an interface by having its methods. So this pass infers the pairs
from method sets and hands them to the shared mechanism, which does the rest
(per-method `dispatches_to` at INFERRED, 0.85 / 0.75 / 0.65 by implementer
count, the single-owner guard). The inferred `implements` pairs only feed the
mechanism; they are not added to the graph.

A named type T implements interface I here when T's methods (value and
pointer receivers alike: the extractor hangs both off T's node) include every
method name I requires. Names only: method nodes carry no signature, and Go has
no overloads to tell apart. The guards:

- Both ends are declared in a `.go` file, as in the C# and Swift passes.
- An interface with no methods (`interface{}`, `any`) or only a type set is
  skipped: every type satisfies the first, and the second is a generics
  constraint, not something a call goes through.
- An interface that embeds another is used only when every embedded interface
  is declared in the corpus, with its methods counted in. `io.Reader` and
  other external interfaces have unknown methods, so such an interface is
  skipped rather than matched on part of its method set.
- An unexported method name (`run()`) can only be implemented in the
  interface's own package, so only types in the same directory count.
- An interface matched by more than `_MAX_IMPLICIT_IMPLEMENTERS` types is
  skipped. Name-only matching makes a lone common name (`Close`, `String`)
  match unrelated types, and past this many the edges say little. The builtin
  `error` and `fmt.Stringer` are not in the corpus, so they never match; a
  local redeclaration of either is matched like any other interface.

Struct embedding is not followed: a type whose method comes from an embedded
field does not own that method node, so it is not matched.
"""
from __future__ import annotations

from pathlib import PurePath

from graphify.interface_dispatch import (
    declared_in,
    method_label,
    resolve_interface_dispatch,
)

_GO_SUFFIXES = (".go",)

# Past this many structural implementers an interface is skipped, not truncated:
# which ten to keep would be arbitrary.
_MAX_IMPLICIT_IMPLEMENTERS = 10


def _is_go_interface(node: dict | None) -> bool:
    meta = (node or {}).get("metadata")
    return isinstance(meta, dict) and meta.get("language") == "go" and meta.get("kind") == "interface"


def resolve_go_interface_dispatch(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Link each Go interface method to the methods of every type that satisfies the interface."""
    interfaces = {n.get("id"): n for n in all_nodes if _is_go_interface(n) and declared_in(n, _GO_SUFFIXES)}
    if not interfaces:
        return
    node_by_id = {n.get("id"): n for n in all_nodes}

    method_names: dict[str, set[str]] = {}
    embeds: dict[str, set[str]] = {}
    type_set_constrained: set[str] = set()
    for e in all_edges:
        rel, source = e.get("relation"), e.get("source")
        if rel == "method":
            mnode = node_by_id.get(e.get("target"))
            if mnode is not None and declared_in(mnode, _GO_SUFFIXES) and method_label(mnode):
                method_names.setdefault(source, set()).add(method_label(mnode))
        elif source in interfaces and rel == "embeds":
            embeds.setdefault(source, set()).add(e.get("target"))
        elif source in interfaces and rel == "references" and e.get("context") == "type_constraint":
            type_set_constrained.add(source)

    def required(iface: str, visiting: frozenset[str] = frozenset()) -> set[str] | None:
        # None: the method set is not fully known (an embedded interface outside
        # the corpus, or an embedding cycle, which Go rejects anyway).
        names = set(method_names.get(iface, ()))
        for embedded in embeds.get(iface, ()):
            if embedded not in interfaces or embedded in visiting:
                return None
            inner = required(embedded, visiting | {iface})
            if inner is None:
                return None
            names |= inner
        return names

    candidates = {
        owner: names for owner, names in method_names.items()
        if owner not in interfaces and declared_in(node_by_id.get(owner), _GO_SUFFIXES)
    }
    inferred: list[dict] = []
    for iface, iface_node in interfaces.items():
        if iface in type_set_constrained or not method_names.get(iface):
            continue
        needed = required(iface)
        if not needed:
            continue
        package = PurePath(str(iface_node.get("source_file"))).parent
        same_package_only = any(not name[:1].isupper() for name in needed)
        impls = [
            owner for owner, names in candidates.items()
            if needed <= names
            and (not same_package_only
                 or PurePath(str(node_by_id[owner].get("source_file"))).parent == package)
        ]
        if 0 < len(impls) <= _MAX_IMPLICIT_IMPLEMENTERS:
            inferred.extend({"source": impl, "target": iface, "relation": "implements"} for impl in impls)
    if not inferred:
        return

    # The shared resolver reads `implements` from the edge list it is given and
    # appends its `dispatches_to` edges to that list; keep only the latter.
    edges = all_edges + inferred
    resolve_interface_dispatch(per_file, all_nodes, edges, suffixes=_GO_SUFFIXES)
    all_edges.extend(edges[len(all_edges) + len(inferred):])
