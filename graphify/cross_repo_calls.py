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
    "go": frozenset({".go"}),
    "java": frozenset({".java"}),
    "kotlin": frozenset({".kt", ".kts"}),
    "objc": frozenset({".h", ".m", ".mm"}),
    "swift": frozenset({".swift"}),
    "php": frozenset({".php", ".phtml", ".php3", ".php4", ".php5", ".php7", ".phps"}),
    "python": frozenset({".py"}),
    # TS and JS share one key: a TS class legitimately answers a JS call site, so
    # splitting them would drop every TS<->JS cross-repo call. An SFC script block is
    # TS/JS too, so a class exported from `.vue` answers as well.
    "typescript": frozenset({".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs",
                             ".vue", ".svelte", ".astro"}),
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
    `Greeter`. Objective-C's ``+``/``-`` sigil is deliberately kept, so an ObjC
    ``-greet`` and a C++ ``.greet()`` stay distinct members of a shared header.
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


def _member_keys(lang: str, callee: str) -> tuple[str, ...]:
    """Which member-index keys a parked callee may answer to.

    An ObjC selector carries no class/instance distinction, so both sigils are
    tried; a type declaring `+greet` and `-greet` both is an ambiguity, not a hit.
    A selector cannot itself begin with a sigil, so stripping one first keeps an
    entry that already carries it from asking for `--greet`.
    """
    if lang == "objc":
        selector = callee.lstrip("+-")
        return (f"-{selector}", f"+{selector}")
    return (callee,)


def _add_cross_repo_edge(merged: "nx.Graph", source: str, target: str, relation: str,
                         caller_data: dict, entry: dict) -> bool:
    if target == source or merged.has_edge(source, target):
        return False
    merged.add_edge(
        source,
        target,
        relation=relation,
        context="cross_repo",
        confidence="INFERRED",
        confidence_score=0.85,
        source_file=str(caller_data.get("source_file") or ""),
        source_location=entry.get("line"),
        weight=1.0,
        _src=source,
        _tgt=target,
        **{CROSS_REPO_CALL_MARKER: True},
    )
    return True


def _link_parked_python_imports(merged: "nx.Graph", parked_nodes: list[tuple[str, dict]]) -> int:
    """Finish parked Python `from module import name` entries by module stem (#3744).

    Python's cross-repo dependency is not receiver-typed: the parked entry names a
    module and a top-level binding in it. It binds when exactly one other-repo
    ``.py`` file node has that stem and exactly one top-level definition (a
    ``contains`` child, so never a method) of that name. An ``imports`` entry
    becomes the file's ``imports`` edge to the definition plus ``imports_from`` to
    the module file; any other entry is a ``calls`` edge from its caller. The
    sourceless placeholder the single-repo build left is not touched: this pass
    adds edges only.
    """
    entries = [(caller, data, entry) for caller, data in parked_nodes
               for entry in _parked_entries(data)
               if entry.get("lang") == "python" and entry.get("module")]
    if not entries:
        return 0

    suffixes = _LANG_SUFFIXES["python"]
    modules: dict[str, list[str]] = defaultdict(list)
    for node, data in merged.nodes(data=True):
        source_file = str(data.get("source_file") or "")
        if not source_file or not data.get("repo") or _suffix(source_file) not in suffixes:
            continue
        if str(data.get("label") or "") != os.path.basename(source_file):
            continue  # a definition, not the module's own file node
        modules[os.path.splitext(os.path.basename(source_file))[0]].append(node)
    if not modules:
        return 0
    module_files = {node for nodes in modules.values() for node in nodes}

    top_level: dict[tuple[str, str], list[str]] = defaultdict(list)
    for u, v, data in merged.edges(data=True):
        if data.get("relation") != "contains":
            continue
        if u in module_files and v not in module_files:
            owner, member = u, v
        elif v in module_files and u not in module_files:
            owner, member = v, u
        else:
            continue
        name = _key(merged.nodes[member].get("label"))
        if name:
            top_level[(owner, name)].append(member)

    added = 0
    for caller, caller_data, entry in entries:
        caller_repo = caller_data.get("repo")
        callee = _key(entry.get("callee"))
        if not caller_repo or not callee:
            continue
        candidates = [node for node in modules.get(str(entry["module"]), [])
                      if merged.nodes[node].get("repo") != caller_repo]
        if len(candidates) != 1:
            continue
        targets = top_level.get((candidates[0], callee), [])
        if len(targets) != 1:
            continue
        if entry.get("relation") == "imports":
            added += _add_cross_repo_edge(merged, caller, targets[0], "imports", caller_data, entry)
            added += _add_cross_repo_edge(merged, caller, candidates[0], "imports_from",
                                          caller_data, entry)
        else:
            added += _add_cross_repo_edge(merged, caller, targets[0], "calls", caller_data, entry)
    return added


def link_cross_repo_member_calls(merged: "nx.Graph") -> int:
    """Emit `calls` edges for parked member calls another repo answers.

    Returns the number of edges added. Idempotent: the pass drops its own earlier
    output first, so re-merging or adding a repo twice cannot duplicate an edge.
    Parked Python module imports are finished here too (#3744).
    """
    _drop_previous_output(merged)
    parked_nodes = [(node, data) for node, data in merged.nodes(data=True)
                    if _parked_entries(data)]
    if not parked_nodes:
        return 0
    added = _link_parked_python_imports(merged, parked_nodes)

    by_name, type_ids = _index_declarations(merged)
    if not by_name:
        return added
    members_by_relation = _index_members(merged, type_ids)

    # C# parked calls need the same namespace/using visibility check as C# type
    # references. Without it, an unresolved third-party receiver such as
    # `FluentValidation.IValidator` can bind to an unrelated `IValidator` that
    # happens to be declared in one merged repository (#3360). Build this only
    # when needed; the other parked languages use their existing suffix guard.
    csharp_resolver = None
    if any(
        str(entry.get("lang") or "") == "csharp"
        for _, data in parked_nodes
        for entry in _parked_entries(data)
    ):
        from graphify.extractors.csharp import CsharpNameResolver

        resolver_nodes = [dict(data, id=node) for node, data in merged.nodes(data=True)]
        resolver_edges = [
            dict(data, source=source, target=target)
            for source, target, data in merged.edges(data=True)
        ]
        csharp_resolver = CsharpNameResolver(resolver_nodes, resolver_edges)

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
            if lang == "csharp":
                # Reuse the extractor's authoritative C# visibility rules. A
                # candidate is valid only when the caller's namespace, using,
                # or alias resolves this exact receiver name to that node.
                resolved, _decisive = csharp_resolver.resolve_type_name(
                    receiver_type,
                    dict(caller_data, id=caller),
                    str(caller_data.get("source_file") or ""),
                )
                if resolved != candidates[0]:
                    continue
            targets: list[str] = []
            for relation in _member_relations(lang):
                members = members_by_relation[relation]
                for member_key in _member_keys(lang, callee):
                    targets.extend(members.get((candidates[0], member_key), []))
                if targets:
                    break
            if len(targets) != 1:
                continue
            added += _add_cross_repo_edge(merged, caller, targets[0], "calls", caller_data, entry)
    return added
