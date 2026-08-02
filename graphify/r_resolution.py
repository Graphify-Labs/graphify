"""Corpus-wide resolution for R calls and sourced files.

R gives an extractor no way to tell a base-R call from a package-internal one:
``paste0(x)`` and ``compute_moments(x)`` are the same syntax, and R has no import
statement that binds either name. Within a package or an analysis directory every
file shares one namespace, so the corpus itself is the only thing that can decide
— which is why ``extractors/r.py`` emits unresolved calls as ``raw_calls`` and
this pass turns them into edges.

Two shapes resolve, both only when the target is unambiguous (the god-node guard
used by the Java and Objective-C resolvers):

  * a call to a name defined exactly once in the corpus -> a ``calls`` edge
  * an R path literal matching exactly one corpus file  -> an ``imports`` edge
    for ``source()``/``sys.source()``, ``references`` for any other caller

Anything defined nowhere is base R or a third-party package and is dropped, so no
hardcoded list of base names is needed and no dangling edge reaches the graph.

Registered into graphify.resolver_registry and run by extract() after id
disambiguation, so node ids and raw_call caller_nids are final.
"""

from __future__ import annotations

from typing import Any

_R_SUFFIXES = (".r",)


def _is_r_file(value: Any) -> bool:
    return str(value or "").lower().endswith(_R_SUFFIXES)


def _path_segments(value: Any) -> tuple[str, ...]:
    """Path split on both separators, so a Windows-authored literal still matches."""
    return tuple(p for p in str(value or "").replace("\\", "/").split("/") if p and p != ".")


def _r_raw_calls(per_file: list[dict]) -> list[dict]:
    calls: list[dict] = []
    for result in per_file:
        if not isinstance(result, dict):
            continue
        for rc in result.get("raw_calls", []) or []:
            if isinstance(rc, dict) and rc.get("lang") == "r":
                calls.append(rc)
    return calls


def resolve_r_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve R calls and sourced-file references against the whole corpus."""
    raw_calls = _r_raw_calls(per_file)
    if not raw_calls:
        return

    node_ids = {n.get("id") for n in all_nodes if isinstance(n, dict)}

    # name -> defining node ids. A function node is labelled `name()`; the file
    # node it lives in is labelled `name.R`, so the suffix keeps them apart.
    definitions: dict[str, set[str]] = {}
    # trailing path segments -> file node id, for `source("a/b.R")` matching.
    files_by_segments: dict[tuple[str, ...], set[str]] = {}
    for node in all_nodes:
        if not isinstance(node, dict) or not _is_r_file(node.get("source_file")):
            continue
        label = str(node.get("label", ""))
        nid = node.get("id")
        if not nid:
            continue
        if label.endswith("()"):
            definitions.setdefault(label[:-2], set()).add(nid)
        elif _is_r_file(label):
            segments = _path_segments(node.get("source_file"))
            for i in range(len(segments)):
                files_by_segments.setdefault(segments[i:], set()).add(nid)

    existing_pairs = {(e.get("source"), e.get("target")) for e in all_edges
                      if isinstance(e, dict)}

    def emit(caller: str, target: str, relation: str, rc: dict, context: str) -> None:
        if caller == target or (caller, target) in existing_pairs:
            return
        existing_pairs.add((caller, target))
        all_edges.append({
            "source": caller,
            "target": target,
            "relation": relation,
            "context": context,
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": rc.get("source_file", ""),
            "source_location": rc.get("source_location"),
            "weight": 1.0,
        })

    for rc in raw_calls:
        caller = rc.get("caller_nid")
        if not caller or caller not in node_ids:
            continue

        if rc.get("kind") == "file_ref":
            targets = files_by_segments.get(_path_segments(rc.get("file_path")), set())
            if len(targets) == 1:
                emit(caller, next(iter(targets)), str(rc.get("relation") or "references"),
                     rc, "import" if rc.get("relation") == "imports" else "reference")
            continue

        targets = definitions.get(str(rc.get("callee") or ""), set())
        if len(targets) == 1:
            emit(caller, next(iter(targets)), "calls", rc, "call")
