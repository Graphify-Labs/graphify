"""Finish member calls that cross a repository boundary in a merged graph (#3152).

A single-repo build can only bind ``obj.method()`` when the receiver's type is
declared in that same build. When the type lives in another repository the
resolver holds the receiver type and drops the call anyway, so ``graph.json`` —
the only artifact ``merge-graphs`` and ``global add`` consume — records nothing,
and no merge-time pass can recover what was never written down. A two-repo call
graph was therefore missing exactly the edges that make it a call graph: eight
edges when the code sits in one corpus, seven after merging the same code from
two repos.

The resolvers now park those calls on the caller node as
``metadata.unresolved_calls`` entries (names only, no node ids — see
``_park_unresolved_member_call``). This pass reads them back after the graphs are
composed and emits the ``calls`` edge when the receiver's type resolves to
exactly one declaration in another repo, keeping the single-definition guard the
single-repo resolvers use: an ambiguous name still fabricates nothing.

Edges only, no node merging or renaming, so the pass composes with the prefixing
and pruning already in place. Every edge it adds is tagged, and it clears its own
previous output before recomputing: ``global add`` composes one repo at a time
and revisits the same pairs on every add, and recomputing from the parked entries
keeps the result identical whether three repos arrived together or one at a time.
"""
from __future__ import annotations

import os
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    import networkx as nx

CROSS_REPO_CALL_MARKER = "_cross_repo_call"
UNRESOLVED_CALLS_KEY = "unresolved_calls"

# A parked entry names the language it was written in, and the declaration that
# answers it must be written in the same one: without this a Java `Greeter` binds
# just as happily to a Python class of the same name in another repo. Extend this
# map when another extractor starts parking calls.
_LANG_SUFFIXES: dict[str, frozenset[str]] = {
    "cpp": frozenset({".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h", ".cu", ".cuh"}),
    "csharp": frozenset({".cs"}),
    "java": frozenset({".java"}),
    "swift": frozenset({".swift"}),
}

# A declaration owns its members through a `method` edge, except in C++, where an
# in-class declaration (`void bar();` in a header) is modelled as a field and
# carries `defines` instead. `method` wins when both name the same member.
_MEMBER_RELATIONS = ("defines", "method")


def _key(label: object) -> str:
    """Normalize a node label or a parked name to its bare identifier.

    Type labels are plain (``Greeter``) while method labels carry the extractor's
    decoration (``.greet()``). Case is preserved: every language that parks calls
    here is case-sensitive, and folding case would let `greeter` answer for
    `Greeter`.
    """
    return str(label or "").strip().removeprefix(".").removesuffix("()")


def _suffix(source_file: object) -> str:
    return os.path.splitext(str(source_file or ""))[1].lower()


def _parked_entries(data: dict) -> list[dict]:
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        return []
    parked = metadata.get(UNRESOLVED_CALLS_KEY)
    if not isinstance(parked, list):
        return []
    return [entry for entry in parked if isinstance(entry, dict)]


def _drop_previous_output(merged: "nx.Graph") -> None:
    """Clear the edges this pass added on an earlier run.

    Recompute-from-scratch is what makes an incremental ``global add`` agree with
    a single ``merge-graphs`` of the same inputs, and it is also how a repo whose
    types moved stops answering for calls it no longer owns.
    """
    stale = [(u, v) for u, v, data in merged.edges(data=True)
             if data.get(CROSS_REPO_CALL_MARKER)]
    merged.remove_edges_from(stale)


def _index_declarations(merged: "nx.Graph") -> tuple[dict[str, list[str]], set[str]]:
    """Index sourced type declarations by bare name. Returns (index, id set)."""
    by_name: dict[str, list[str]] = defaultdict(list)
    type_ids: set[str] = set()
    for node, data in merged.nodes(data=True):
        if not data.get("_callable_class") or not data.get("source_file"):
            continue
        if not data.get("repo"):
            continue
        name = _key(data.get("label"))
        if not name:
            continue
        by_name[name].append(node)
        type_ids.add(node)
    return by_name, type_ids


def _index_members(
    merged: "nx.Graph", type_ids: set[str]
) -> dict[str, dict[tuple[str, str], list[str]]]:
    """Index each declaration's members by relation, then by name.

    The merged graph is undirected, and a ``method`` edge carries no reliable
    direction once composed, so the owner is identified as the endpoint that is a
    type declaration. A nested declaration puts a type on both ends; that pair is
    skipped rather than guessed at.

    Kept per relation rather than pooled: ``defines`` covers fields as well as
    C++'s in-class member declarations, so only a language that needs it may look
    there, and only when no ``method`` of that name exists.
    """
    by_relation: dict[str, dict[tuple[str, str], list[str]]] = {
        relation: defaultdict(list) for relation in _MEMBER_RELATIONS
    }
    for u, v, data in merged.edges(data=True):
        relation = data.get("relation")
        if relation not in by_relation:
            continue
        if u in type_ids and v not in type_ids:
            owner, member = u, v
        elif v in type_ids and u not in type_ids:
            owner, member = v, u
        else:
            continue
        name = _key(merged.nodes[member].get("label"))
        if name:
            by_relation[relation][(owner, name)].append(member)
    return by_relation


def _member_relations(lang: str) -> tuple[str, ...]:
    """Which owner→member relations may answer a call parked by ``lang``.

    Only C++ models an in-class declaration (``void bar();`` in a header) as a
    field, so only a C++ entry may fall back to ``defines``; for every other
    language a ``defines`` target is a field, and a field cannot answer a call.
    """
    return ("method", "defines") if lang == "cpp" else ("method",)


def link_cross_repo_member_calls(merged: "nx.Graph") -> int:
    """Emit `calls` edges for parked member calls another repo answers.

    Returns the number of edges added. Idempotent: the pass drops its own earlier
    output first, so re-merging or adding a repo twice cannot duplicate an edge.
    """
    _drop_previous_output(merged)
    parked_nodes = [(node, data) for node, data in merged.nodes(data=True)
                    if _parked_entries(data)]
    if not parked_nodes:
        return 0

    by_name, type_ids = _index_declarations(merged)
    if not by_name:
        return 0
    members_by_relation = _index_members(merged, type_ids)

    added = 0
    for caller, caller_data in parked_nodes:
        caller_repo = caller_data.get("repo")
        if not caller_repo:
            # Without a repo tag "another repo" has no meaning, and this pass
            # deliberately never re-decides a call inside one repo.
            continue
        for entry in _parked_entries(caller_data):
            lang = str(entry.get("lang") or "")
            suffixes = _LANG_SUFFIXES.get(lang)
            receiver_type = _key(entry.get("receiver_type"))
            callee = _key(entry.get("callee"))
            if not suffixes or not receiver_type or not callee:
                continue
            candidates = [
                node for node in by_name.get(receiver_type, [])
                if merged.nodes[node].get("repo") != caller_repo
                and _suffix(merged.nodes[node].get("source_file")) in suffixes
            ]
            if len(candidates) != 1:
                # The same guard the single-repo resolvers apply: two repos
                # declaring the same name is an ambiguity, not a hit.
                continue
            targets: list[str] = []
            for relation in _member_relations(lang):
                targets = members_by_relation[relation].get((candidates[0], callee), [])
                if targets:
                    break
            if len(targets) != 1:
                continue
            target = targets[0]
            if target == caller or merged.has_edge(caller, target):
                continue
            merged.add_edge(
                caller,
                target,
                relation="calls",
                context="cross_repo",
                confidence="INFERRED",
                confidence_score=0.8,
                source_file=str(caller_data.get("source_file") or ""),
                source_location=entry.get("line"),
                weight=1.0,
                _src=caller,
                _tgt=target,
                **{CROSS_REPO_CALL_MARKER: True},
            )
            added += 1
    return added
