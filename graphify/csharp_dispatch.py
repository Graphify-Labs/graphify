"""Member-level interface dispatch for C# (#3003).

A C# call through a constructor-injected dependency lands on the interface's
method node, because that is what the call site names: `_report.Build()` where
`_report` is an `IReport` resolves to `IReport.Build()`. The implementing
`Report.Build()` is a separate node, and nothing joins the two, so a directed
walk stops at the interface and every chain through an injected dependency is
cut at that point. On a Scrutor-scanned .NET service where every dependency is
an interface, that is most chains.

This resolver runs after all files are extracted, with the merged corpus
available, and links the interface's method to the implementing method:

    ireport_ireport_build  --dispatches_to-->  report_report_build

It only fires when the interface has exactly one implementer and that
implementer owns exactly one method of the same name, the single-owner guard
`resolve_pascal_inherited_calls` and `resolve_ruby_member_calls` already use.
Walking `implements` to the one type that can serve the call mirrors what the
runtime does; guessing among several implementers would not, so anything
ambiguous is left alone.

The join is per method rather than per call site, so one edge reconnects every
call that reaches the interface method. Confidence is `INFERRED`: the target is
forced once there is a single implementer, but the source text never names it.
"""
from __future__ import annotations

_CSHARP_SUFFIXES = (".cs",)

DISPATCH_RELATION = "dispatches_to"


def _method_label(node: dict) -> str:
    """Normalize a method node's label to its bare name for matching."""
    return str(node.get("label", "")).strip().removeprefix(".").removesuffix("()").lower()


def resolve_csharp_interface_dispatch(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Link each single-implementer interface method to its implementation.

    Purely additive: the existing call edge to the interface method is left in
    place, since the call site really does name the interface.
    """
    if not any(
        str(result.get("source_file", "")).endswith(_CSHARP_SUFFIXES)
        for result in per_file
        if isinstance(result, dict)
    ) and not any(
        str(n.get("source_file", "")).endswith(_CSHARP_SUFFIXES) for n in all_nodes
    ):
        return

    node_by_id = {n.get("id"): n for n in all_nodes}

    implementers: dict[str, set[str]] = {}
    methods_of: dict[str, dict[str, set[str]]] = {}
    for e in all_edges:
        rel = e.get("relation")
        if rel == "implements":
            implementers.setdefault(e.get("target"), set()).add(e.get("source"))
        elif rel == "method":
            owner, method_nid = e.get("source"), e.get("target")
            mnode = node_by_id.get(method_nid)
            if mnode is None:
                continue
            name = _method_label(mnode)
            if name:
                # A set, so the same method arriving on two `method` edges cannot
                # look like two same-named methods and trip the guard below.
                methods_of.setdefault(owner, {}).setdefault(name, set()).add(method_nid)

    if not implementers or not methods_of:
        return

    existing_pairs = {(e.get("source"), e.get("target")) for e in all_edges}
    new_edges: list[dict] = []

    for interface_nid, impls in implementers.items():
        if len(impls) != 1:
            continue
        impl_nid = next(iter(impls))
        interface_node = node_by_id.get(interface_nid)
        impl_node = node_by_id.get(impl_nid)
        if interface_node is None or impl_node is None:
            continue
        # Both ends must be real declarations: a sourceless stub minted for a
        # dangling reference carries no members worth dispatching to.
        if not interface_node.get("source_file") or not impl_node.get("source_file"):
            continue
        if not str(interface_node.get("source_file", "")).endswith(_CSHARP_SUFFIXES):
            continue

        impl_methods = methods_of.get(impl_nid, {})
        for name, declared in methods_of.get(interface_nid, {}).items():
            if len(declared) != 1:
                continue
            candidates = impl_methods.get(name, set())
            if len(candidates) != 1:
                continue
            source = next(iter(declared))
            target = next(iter(candidates))
            if source == target or (source, target) in existing_pairs:
                continue
            existing_pairs.add((source, target))
            new_edges.append({
                "source": source,
                "target": target,
                "relation": DISPATCH_RELATION,
                "context": "call",
                "confidence": "INFERRED",
                "confidence_score": 0.9,
                "source_file": str(impl_node.get("source_file", "")),
                "source_location": impl_node.get("source_location"),
                "weight": 1.0,
            })

    all_edges.extend(new_edges)
