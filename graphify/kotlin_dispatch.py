"""Member-level interface dispatch for Kotlin.

`g.greet()` on a `g: Greeter` resolves to the interface's own `.greet()`,
because that is what the call site names. Each implementing `override fun
greet()` is a separate node, so this pass links the interface method to every
implementer through `graphify.interface_dispatch`, as C# and Swift do.

Both ends must be declared in a Kotlin file: `implements` is resolved by name,
and a Java class implementing a Kotlin interface needs the Java extractor's own
evidence before it is claimed here.
"""
from __future__ import annotations

from graphify.interface_dispatch import resolve_interface_dispatch

_KOTLIN_SUFFIXES = (".kt", ".kts")


def resolve_kotlin_interface_dispatch(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Link each Kotlin interface method to every implementer that owns it unambiguously."""
    resolve_interface_dispatch(per_file, all_nodes, all_edges, suffixes=_KOTLIN_SUFFIXES)
