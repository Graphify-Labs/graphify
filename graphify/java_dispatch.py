"""Member-level interface dispatch for Java.

`this.worker.run()` on a field typed with the interface `Worker` resolves to
`Worker.run()`, because that is what the call site names. The implementing
`EmailWorker.run()` is a separate node with nothing joining the two, so a
directed walk stops at the interface: the Java twin of the C# gap #3003 closed.

The Java extractor already emits `implements` (from classes, enums and records,
generic or nested interfaces included) and `method` edges for interface
members, so this module only fixes the `.java` gate over
`graphify.interface_dispatch`. Both ends of a pair must be declared in a
`.java` file: `implements` is resolved by name, so a C# or Kotlin type with the
same name is a collision, not an implementation.

Known limits, each pinned by a test:

- An abstract class and its subclasses (`extends`) arrive as `inherits`, which
  this pass does not read: a base method may well be the real target.
- An interface that extends another is not walked transitively.
- A `default` method nobody overrides owns no candidate in the implementer, so
  the call really does land on the interface and gets no edge.
- One interface method and one implementer method of a name pair up without
  comparing signatures (the shared one-to-one rule), so `send(int, int)` is
  linked even when the real `send(String)` is inherited from a base class.
- `implements a.Worker` written fully qualified, with no import, binds to a
  sourceless stub, so it gets no edge; the imported form links.
"""
from __future__ import annotations

from graphify.interface_dispatch import resolve_interface_dispatch

_JAVA_SUFFIXES = (".java",)


def resolve_java_interface_dispatch(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Link each Java interface method to every implementation that owns it unambiguously."""
    resolve_interface_dispatch(per_file, all_nodes, all_edges, suffixes=_JAVA_SUFFIXES)
