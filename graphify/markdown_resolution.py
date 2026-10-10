"""Cross-file resolution of code-span mentions in Markdown documents.

``extract_markdown`` reports every inline code span that reads as a symbol
name (``Widget``, ``render()``, ``pkg.Widget``, ``src/mod.py::Widget::render``)
as a ``raw_calls`` entry tagged ``language: "markdown"`` instead of guessing a
target id: the symbol is defined in some other file, and only once every file
is extracted and the id-remap passes have run can the mention be matched to
the node that actually exists. Riding the ``raw_calls`` channel means those
passes rewrite the mention's ``caller_nid`` alongside every other raw call,
and the extraction cache round-trips it for free.

This resolver runs from the language-resolver registry (see
``resolver_registry``) with the merged corpus in hand and turns each mention
into a ``references`` edge from the heading (or page) that cites the symbol
to the code node that defines it:

* a path-qualified mention resolves against the cited file only. The file is
  matched by its path relative to the document, then as a segment-aligned
  suffix of a scanned file, and must be unique; the symbol chain is walked
  through ``contains`` / ``method`` edges so ``mod.py::Widget::render`` is
  the ``render`` owned by ``Widget``. The document names the file and the
  symbol verbatim, so the edge is EXTRACTED;
* a bare mention resolves only when exactly one callable or type in the
  corpus carries that label (case-sensitive; language built-ins excluded).
  Only nodes the extractors marked ``_callable`` qualify, for the reason the
  indirect-call pass gives (#1566): a by-name match must land on a real
  function, method or class, never on a same-named data symbol such as a
  JSON key. A dotted mention (``pkg.Widget``, ``Widget.render``) keeps its
  qualifiers, and a candidate survives only when every qualifier is a label
  on its ``contains`` / ``method`` owner chain or a segment (or stem) of its
  source path: ``time.sleep`` never lands on a repo's own ``sleep``, and
  ``Widget.render`` picks the ``render`` that ``Widget`` owns. No other
  tie-breaking: an ambiguous name is a guess, and a guess is not an edge.
  The match is INFERRED (0.95, a named cross-file reference).

An explicit relative cite (``./`` or ``../``) resolves against the document's
directory only; it never falls through to the suffix rule, so a path that
escapes the corpus cannot land on an unrelated copy of the file elsewhere.

The shared cross-file call pass in ``extract`` skips ``markdown`` raw calls,
so a mention never surfaces as a ``calls`` edge.
"""
from __future__ import annotations

import os
import re
from typing import Any

from graphify.extractors.base import _LANGUAGE_BUILTIN_GLOBALS

MARKDOWN_MENTION_SUFFIXES = frozenset({".md", ".mdx", ".qmd", ".skill"})

_CONTAINMENT_RELATIONS = frozenset({"contains", "method"})

#: Leading ``./`` and ``../`` segments of a cited path, stripped as whole
#: segments (``lstrip("./")`` would eat the dot of ``.github/...``).
_RELATIVE_PREFIX_RE = re.compile(r"^(\.\.?/)+")


def _symbol_label(node: dict[str, Any]) -> str:
    """A node's label as a document would write it: no ``()``, no leading dot."""
    return str(node.get("label", "")).strip("()").lstrip(".")


def _is_file_node(node: dict[str, Any]) -> bool:
    label = str(node.get("label", ""))
    source_file = str(node.get("source_file", ""))
    return bool(source_file) and label == os.path.basename(source_file)


def _posix(path: str) -> str:
    return path.replace("\\", "/")


def _match_cited_file(cited: str, doc_file: str, source_files: set[str]) -> str | None:
    """The scanned source file a ``path::Name`` mention names, or None.

    Tries the path relative to the citing document first (``../src/mod.py``
    from ``docs/guide.md``), then an exact match, then a unique
    segment-aligned suffix (``src/mod.py`` naming ``/repo/src/mod.py``). A
    cite that is explicitly relative (``./x`` or ``../x``) stops after the
    first step: it names one location, and a suffix match elsewhere would be a
    different file.
    """
    cited_posix = _posix(cited)
    doc_dir = os.path.dirname(doc_file)
    relative = _posix(os.path.normpath(os.path.join(doc_dir, cited_posix)))
    if relative in source_files:
        return relative
    if cited_posix.startswith(("./", "../")):
        return None
    if cited_posix in source_files:
        return cited_posix
    stripped = _RELATIVE_PREFIX_RE.sub("", cited_posix)
    matches = [sf for sf in source_files
               if sf == stripped or sf.endswith("/" + stripped)]
    return matches[0] if len(matches) == 1 else None


def _evidence(node_id: str, nodes_by_id: dict[str, dict[str, Any]],
              parents: dict[str, set[str]]) -> set[str]:
    """Labels a dotted mention may qualify ``node_id`` with.

    The labels of every node on its ``contains`` / ``method`` owner chain
    (``Widget`` for ``Widget.render``) plus each segment and stem of its
    source path (``pkg`` and ``mod`` for ``pkg.mod.Widget``).
    """
    evidence: set[str] = set()
    frontier = {node_id}
    seen: set[str] = set()
    while frontier:
        nid = frontier.pop()
        if nid in seen:
            continue
        seen.add(nid)
        owners = parents.get(nid, set())
        for owner in owners:
            node = nodes_by_id.get(owner)
            if node is not None:
                evidence.add(_symbol_label(node))
        frontier |= owners
    node = nodes_by_id.get(node_id, {})
    for segment in _posix(str(node.get("source_file", ""))).split("/"):
        if segment:
            evidence.add(segment)
            evidence.add(os.path.splitext(segment)[0])
    return evidence


def _markdown_raw_calls(per_file: list[dict]) -> list[dict]:
    calls: list[dict] = []
    for result in per_file:
        if not isinstance(result, dict):
            continue
        for rc in result.get("raw_calls", []) or []:
            if isinstance(rc, dict) and rc.get("language") == "markdown":
                calls.append(rc)
    return calls


def resolve_markdown_mentions(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Turn ``language: "markdown"`` raw calls into ``references`` edges in place."""
    mentions = _markdown_raw_calls(per_file)
    if not mentions:
        return

    code_nodes = [
        n for n in all_nodes
        if n.get("id") and n.get("file_type") == "code" and not _is_file_node(n)
    ]
    by_label: dict[str, list[str]] = {}
    by_file: dict[str, dict[str, list[str]]] = {}
    for n in code_nodes:
        label = _symbol_label(n)
        if not label:
            continue
        if n.get("_callable"):
            by_label.setdefault(label, []).append(n["id"])
        source_file = _posix(str(n.get("source_file", "")))
        if source_file:
            by_file.setdefault(source_file, {}).setdefault(label, []).append(n["id"])
    source_files = set(by_file)

    parents: dict[str, set[str]] = {}
    for e in all_edges:
        if e.get("relation") in _CONTAINMENT_RELATIONS:
            parents.setdefault(str(e.get("target")), set()).add(str(e.get("source")))
    nodes_by_id = {n["id"]: n for n in all_nodes if n.get("id")}
    node_ids = set(nodes_by_id)
    existing = {
        (e.get("source"), e.get("target"))
        for e in all_edges if e.get("relation") == "references"
    }

    def _resolve_chain(file_labels: dict[str, list[str]], names: list[str]) -> str | None:
        candidates = list(file_labels.get(names[-1], []))
        for depth, owner_name in enumerate(reversed(names[:-1]), start=1):
            owners = set(file_labels.get(owner_name, []))
            narrowed = []
            for c in candidates:
                chain = {c}
                for _ in range(depth):
                    chain = {p for nid in chain for p in parents.get(nid, ())}
                if chain & owners:
                    narrowed.append(c)
            candidates = narrowed
        return candidates[0] if len(candidates) == 1 else None

    for rc in mentions:
        caller = str(rc.get("caller_nid", ""))
        callee = str(rc.get("callee", "")).strip()
        if not caller or not callee or caller not in node_ids:
            continue
        names = list(rc.get("qualifiers") or []) + [callee]
        cited = rc.get("path")
        if cited:
            source_file = _match_cited_file(
                str(cited), _posix(str(rc.get("source_file", ""))), source_files
            )
            if source_file is None:
                continue
            target = _resolve_chain(by_file[source_file], names)
            confidence, score = "EXTRACTED", 1.0
        else:
            if callee in _LANGUAGE_BUILTIN_GLOBALS:
                continue
            qualifiers = set(names[:-1])
            candidates = [
                c for c in by_label.get(callee, [])
                if qualifiers <= _evidence(c, nodes_by_id, parents)
            ]
            target = candidates[0] if len(candidates) == 1 else None
            confidence, score = "INFERRED", 0.95
        if target is None or target == caller or (caller, target) in existing:
            continue
        existing.add((caller, target))
        all_edges.append({
            "source": caller,
            "target": target,
            "relation": "references",
            "context": rc.get("context", ""),
            "confidence": confidence,
            "confidence_score": score,
            "source_file": rc.get("source_file", ""),
            "source_location": rc.get("source_location"),
            "weight": 1.0,
        })
