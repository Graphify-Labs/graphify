"""Join the same declared type across repositories in a merged graph (#3007).

`merge-graphs` prefixes every node id with its repo tag, so a contract type that
two services both declare arrives as two unconnected nodes. In a message-bus
codebase that is exactly where the interesting hop lives: the producer references
`SyncProductUpsertToSearchEvent` in one repo, the consumer implements
`IConsumer<SyncProductUpsertToSearchEvent>` in the other, and the merged graph has
no way to get from one to the other even though both sides name the same type.

This pass adds a `same_type_as` edge between type declarations that share both a
namespace and a name and come from different repos. Requiring the namespace keeps
it to types that were declared identically rather than two classes that merely
picked the same short name: on a pair of .NET services with 1440 and 262 declared
types, the namespace-plus-name match produced 7 pairs, all of them the shared
`EventManager.Models.*Event` contracts, and nothing else.

Edges only, no node merging. Two repos can hold copies of a contract that have
drifted, and collapsing them would hide that; a link lets a traversal cross while
each side keeps its own members, file and provenance.
"""
from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    import networkx as nx

SHARED_TYPE_RELATION = "same_type_as"


def link_shared_type_declarations(merged: "nx.Graph") -> int:
    """Link identically declared types across repos. Returns the edge count added.

    A candidate node is a sourced type declaration carrying a namespace and a
    repo tag. A group qualifies when its members span at least two repos, and
    every pair inside a qualifying group gets one edge. Groups are the handful of
    types two repos genuinely share, so the pairwise walk stays small.
    """
    by_declaration: dict[tuple[str, str], list[str]] = defaultdict(list)
    for node, data in merged.nodes(data=True):
        if not data.get("_callable_class") or not data.get("source_file"):
            continue
        namespace = str((data.get("metadata") or {}).get("namespace") or "")
        label = str(data.get("label") or "")
        if not namespace or not label or not data.get("repo"):
            continue
        by_declaration[(namespace, label)].append(node)

    added = 0
    for (namespace, label), nodes in by_declaration.items():
        if len(nodes) < 2:
            continue
        if len({merged.nodes[n].get("repo") for n in nodes}) < 2:
            continue
        for index, left in enumerate(nodes):
            for right in nodes[index + 1:]:
                if merged.nodes[left].get("repo") == merged.nodes[right].get("repo"):
                    continue
                if merged.has_edge(left, right):
                    continue
                merged.add_edge(
                    left,
                    right,
                    relation=SHARED_TYPE_RELATION,
                    context="cross_repo",
                    confidence="INFERRED",
                    confidence_score=0.9,
                    source_file=str(merged.nodes[left].get("source_file") or ""),
                    weight=1.0,
                    _src=left,
                    _tgt=right,
                )
                added += 1
    return added
