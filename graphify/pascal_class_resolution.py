"""Cross-file resolution of Pascal/Delphi base classes to their declaration.

The per-file extractors resolve a base class name with
``_pascal_resolve_class``, which maps a name to a file by NAMING CONVENTION
alone: ``TFooBar`` is assumed to live in ``FooBar.pas``. When no such file
exists the extractor creates a stub node in the inheriting file instead, as it
must -- a single file cannot know where a name it does not declare comes from.

The convention holds for RTL-style code and breaks on most real Delphi. A base
class declared in a unit named anything else -- ``TXForm`` in ``XFormP.pas``,
``TPrzodek`` in ``Obiekty.pas`` -- produces one private stub per inheriting
file, so an inheritance hierarchy that is one tree in the compiler arrives in
the graph as hundreds of disconnected two-node fragments. Two things break
with it:

- "what inherits from X" answers with one class instead of hundreds, and
- ``resolve_pascal_inherited_calls`` walks the ``inherits`` chain to resolve a
  call to an inherited method, so a chain severed at its first link resolves
  almost nothing.

This resolver runs after all files are extracted, with the full corpus
available, and retargets those ``inherits`` edges onto the node where the class
is actually declared. It is registered BEFORE ``pascal_inherited_calls`` so the
call resolver walks a repaired chain.

A declared class is distinguished from a stub structurally: the extractor emits
a ``contains`` edge from the enclosing module/file node to every type it
declares, and nothing contains a stub. The retarget then requires a unique
declaration -- preferring one in a unit the inheriting file actually imports,
exactly as the compiler would -- and leaves the stub untouched when the name is
ambiguous or unknown, so an external base class (``IDispatch``, RTL types)
keeps the graph it has today.
"""
from __future__ import annotations

_PASCAL_SUFFIXES = (".pas", ".pp", ".dpr", ".dpk", ".inc")


def _is_pascal(source_file: object) -> bool:
    return isinstance(source_file, str) and source_file.lower().endswith(_PASCAL_SUFFIXES)


def resolve_pascal_base_classes(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Point Pascal ``inherits`` edges at the class's real declaration.

    Mutates ``all_edges`` in place (retargeting, then deduplicating). The stub
    node the extractor created in the inheriting file is left in place once its
    ``inherits`` edge is retargeted; it becomes an orphan (at most one per
    inheriting file), which is harmless graph noise. Keeping it avoids changing
    the node-list length, which the incremental-rebuild scratch slice relies on.
    Purely a repair: no new relation is introduced and no edge is created
    between classes that were not already related by an ``inherits`` the
    extractor emitted.
    """
    node_by_id = {n.get("id"): n for n in all_nodes}

    # A type the extractor saw declared: something `contains` it. Stubs are
    # contained by nothing.
    declared_ids: set[str] = set()
    # file path -> files it imports, for use-clause-scoped disambiguation.
    imports_of: dict[str, set[str]] = {}
    for edge in all_edges:
        relation = edge.get("relation")
        if relation == "contains":
            declared_ids.add(edge.get("target"))
        elif relation == "imports":
            source = node_by_id.get(edge.get("source"), {}).get("source_file")
            target = node_by_id.get(edge.get("target"), {}).get("source_file")
            if isinstance(source, str) and isinstance(target, str):
                imports_of.setdefault(source, set()).add(target)

    # Declared Pascal types, by name. Pascal is case-insensitive.
    by_name: dict[str, list[str]] = {}
    for node in all_nodes:
        nid = node.get("id")
        if nid not in declared_ids or not _is_pascal(node.get("source_file")):
            continue
        label = str(node.get("label", ""))
        # Routines render as `Name()`; only types can be inherited from.
        if label.endswith("()") or not label:
            continue
        by_name.setdefault(label.lower(), []).append(nid)
    if not by_name:
        return

    def _declaration_for(name: str, from_file: object) -> str | None:
        """The unique declaration of *name* visible to *from_file*, if any."""
        candidates = by_name.get(name.lower())
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        # Several units declare this name: let the inheriting file's own uses
        # clause pick, the way the compiler's unit scope would.
        visible = imports_of.get(from_file, set()) if isinstance(from_file, str) else set()
        scoped = [
            nid for nid in candidates
            if node_by_id.get(nid, {}).get("source_file") in visible
        ]
        return scoped[0] if len(scoped) == 1 else None

    # Edges are retargeted in place, never added or removed: on an incremental
    # rebuild the framework hands resolvers SCRATCH lists and keeps only what
    # was appended (`_rl_edges[_e0:]`), so changing a list's length here would
    # shift that slice and copy unrelated edges into the graph. Mutating the
    # edge dicts themselves is safe — the scratch list holds the same objects.
    existing_pairs = {
        (e.get("source"), e.get("target"))
        for e in all_edges if e.get("relation") == "inherits"
    }
    for edge in all_edges:
        if edge.get("relation") != "inherits":
            continue
        target_id = edge.get("target")
        if target_id in declared_ids:
            continue  # already points at a real declaration
        stub = node_by_id.get(target_id)
        source = node_by_id.get(edge.get("source"))
        if stub is None or source is None or not _is_pascal(source.get("source_file")):
            continue
        declaration = _declaration_for(str(stub.get("label", "")), source.get("source_file"))
        if declaration is None or declaration == edge.get("source"):
            continue
        pair = (edge.get("source"), declaration)
        if pair in existing_pairs:
            # Two stubs in one file collapsing onto the same declaration would
            # duplicate the edge. Leaving this one on its stub keeps the graph
            # free of parallel `inherits` edges without deleting anything.
            continue
        existing_pairs.add(pair)
        edge["target"] = declaration
