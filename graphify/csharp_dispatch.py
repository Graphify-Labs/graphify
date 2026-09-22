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


def _is_csharp(node: dict | None) -> bool:
    """True when the node is a declaration that lives in a C# file.

    Every end of a dispatch pair has to pass this. `implements` is resolved by
    name, so in a mixed corpus a Java class declaring `implements IReport` binds
    to a C# `IReport` when that is the only node with the name, and linking a C#
    interface member to a Java method would be a wrong edge rather than a missing
    one. A non-C# implementation of a C# interface, from VB or a Razor component,
    is a real thing, but claiming it needs its own extractor evidence.
    """
    if not node:
        return False
    source_file = node.get("source_file")
    return bool(source_file) and str(source_file).endswith(_CSHARP_SUFFIXES)


def _method_label(node: dict) -> str:
    """Return a method node's bare name, for matching.

    Case is kept: C# is case sensitive, and an implementing member must spell the
    interface member exactly, so folding case could only pair a declaration with
    a member that does not implement it.

    The name is cut at the first parenthesis rather than by stripping a trailing
    `()`. Today the C# extractor labels every method `.Name()`, so the two are the
    same, but the pair match is keyed on this string and a label that ever carried
    a signature would silently stop matching instead of failing visibly.
    """
    label = str(node.get("label", "")).strip().removeprefix(".")
    return label.split("(", 1)[0]


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
            if mnode is None or not _is_csharp(mnode):
                continue
            name = _method_label(mnode)
            if name:
                # A set, so the same method arriving on two `method` edges cannot
                # look like two same-named methods and trip the guard below.
                methods_of.setdefault(owner, {}).setdefault(name, set()).add(method_nid)

    if not implementers or not methods_of:
        return

    # Scoped to this relation: another edge between the two members, whatever it
    # is, says nothing about whether the dispatch link is already there.
    existing_pairs = {
        (e.get("source"), e.get("target"))
        for e in all_edges
        if e.get("relation") == DISPATCH_RELATION
    }
    new_edges: list[dict] = []

    for interface_nid, impls in implementers.items():
        if len(impls) != 1:
            continue
        impl_nid = next(iter(impls))
        interface_node = node_by_id.get(interface_nid)
        impl_node = node_by_id.get(impl_nid)
        if interface_node is None or impl_node is None:
            continue
        # Both ends must be C# declarations. A sourceless stub minted for a
        # dangling reference carries no members worth dispatching to, and a
        # cross-language pair is a name collision rather than an implementation.
        if not _is_csharp(interface_node) or not _is_csharp(impl_node):
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
