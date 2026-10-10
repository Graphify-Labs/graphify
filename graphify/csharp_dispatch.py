"""Member-level interface dispatch for C# (#3003).

A C# call through a constructor-injected dependency lands on the interface's
method node, because that is what the call site names: `_report.Build()` where
`_report` is an `IReport` resolves to `IReport.Build()`. The implementing
`Report.Build()` is a separate node, and nothing joins the two, so a directed
walk stops at the interface and every chain through an injected dependency is
cut at that point. On a Scrutor-scanned .NET service where every dependency is
an interface, that is most chains.

The mechanism — single-implementer, single-owner, per-method `dispatches_to`
edges at INFERRED — lives in `graphify.interface_dispatch` so that another
language can add a gate rather than a copy; this module fixes the C# gate.
Both ends of a pair must be declared in a `.cs` file: `implements` is
resolved by name, so in a mixed corpus a Java class declaring
`implements IReport` binds to a C# `IReport` when that is the only node with
the name, and linking a C# interface member to a Java method would be a wrong
edge rather than a missing one. A non-C# implementation of a C# interface,
from VB or a Razor component, is a real thing, but claiming it needs its own
extractor evidence.
"""
from __future__ import annotations

from graphify.interface_dispatch import (  # noqa: F401  (re-exported for callers)
    DISPATCH_RELATION,
    method_label as _method_label,
    resolve_interface_dispatch,
)

_CSHARP_SUFFIXES = (".cs",)


def resolve_csharp_interface_dispatch(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Link each single-implementer C# interface method to its implementation."""
    resolve_interface_dispatch(per_file, all_nodes, all_edges, suffixes=_CSHARP_SUFFIXES)
