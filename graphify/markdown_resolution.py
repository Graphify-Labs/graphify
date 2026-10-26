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
  A bare, parenthesis-less method name is held to one more test: a word like
  ``redis`` is prose as often as it is a reference, so a method match survives
  only when the citing section also names the class that owns it (#4609).
  A bare free function name is held to the same test with its defining file in
  place of the owner class: prose-like words (``token``, ``raw``) require the
  citing section to cite that file or a symbol from it (#4804). Evidence is
  section-scoped. Classes, snake_case, camelCase, trailing ``()``, or PascalCase
  in export languages carry sufficient evidence on their own. Links to scanned
  source files also mint doc->file references edges.
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
from pathlib import Path
from typing import Any

from graphify.extractors.base import (
    _LANGUAGE_BUILTIN_GLOBALS,
    active_scan_root as _active_scan_root,
)

MARKDOWN_MENTION_SUFFIXES = frozenset({".md", ".mdx", ".qmd", ".skill"})

_CONTAINMENT_RELATIONS = frozenset({"contains", "method"})

#: Leading ``./`` and ``../`` segments of a cited path, stripped as whole
#: segments (``lstrip("./")`` would eat the dot of ``.github/...``).
_RELATIVE_PREFIX_RE = re.compile(r"^(\.\.?/)+")


def _symbol_label(node: dict[str, Any]) -> str:
    """A node's label as a document would write it: no ``()``, no leading dot."""
    return str(node.get("label", "")).strip("()").lstrip(".")


_CAMEL_CASE_RE = re.compile(r'[a-z][A-Z]')

# Languages where exported identifiers are PascalCase by convention (#4804).
_PASCAL_EXPORT_SUFFIXES = frozenset({
    ".go", ".cs", ".vb", ".swift", ".scala", ".pas", ".dpr", ".lpr",
    ".ps1", ".psm1",
})


def _is_prose_like_label(label: str) -> bool:
    """Whether a bare label looks like ordinary prose rather than a distinct code identifier.

    Distinct code identifiers — snake_case (containing ``_``) or camelCase (a
    lowercase letter followed by uppercase) — are exempt from the bare
    free-function evidence test (#4804), while plain single-word lowercase
    names (``token``, ``raw``, ``fail``, ``config``) require evidence. A
    PascalCase label is exempt only in a PascalCase-export language, checked
    by the caller against the target's source file.
    """
    return "_" not in label and not _CAMEL_CASE_RE.search(label)


def _is_pascal_case_export_language(source_file: str) -> bool:
    """Whether *source_file*'s language exports identifiers as PascalCase."""
    return os.path.splitext(_posix(source_file))[1].lower() in _PASCAL_EXPORT_SUFFIXES


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
    return _cited_file_suffix(cited_posix, source_files)


def _cited_file_suffix(cited_posix: str, source_files: set[str]) -> str | None:
    """The scanned file a normalized cite names by unique segment-aligned suffix."""
    stripped = _RELATIVE_PREFIX_RE.sub("", cited_posix)
    matches = [sf for sf in source_files
               if sf == stripped or sf.endswith("/" + stripped)]
    return matches[0] if len(matches) == 1 else None


def _match_cited_file_any_form(cited: str, doc_file: str,
                               source_files: set[str], *,
                               form_mismatch: bool,
                               scan_root: "Path | str | None" = None) -> str | None:
    """Resolve a cited file even when a partial rebuild mixes path forms.

    Preserved nodes carry project-relative ``source_file`` values while a
    freshly re-extracted document may carry an absolute one, so the
    document-relative join in :func:`_match_cited_file` can miss a file that is
    in the corpus. The suffix fallback fires only when that mixing is detected
    (an absolute citing document against a corpus with relative paths) — with
    uniform path forms the explicit-relative discipline above holds unchanged.
    The result licenses evidence and doc->file citations, both anchored to
    corpus files, so a unique corpus path that is a suffix of the joined path
    is the file the document's own directory tree names.
    """
    matched = _match_cited_file(cited, doc_file, source_files)
    if matched is not None or not form_mismatch:
        return matched
    root = _posix(str(scan_root)) if scan_root is not None else None
    if root is None:
        active = _active_scan_root()
        if active is not None:
            root = _posix(str(active))
    joined = _posix(os.path.normpath(
        os.path.join(os.path.dirname(_posix(doc_file)), _posix(cited))))
    if root is not None:
        try:
            rel = _posix(os.path.relpath(joined, root))
        except ValueError:
            return None
        if rel.startswith("..") or os.path.isabs(rel):
            return None
        matches = [sf for sf in source_files if rel == sf or rel.endswith("/" + sf)]
        return matches[0] if len(matches) == 1 else None

    matches = []
    doc_posix = _posix(doc_file)
    for sf in source_files:
        if joined == sf:
            matches.append(sf)
        elif joined.endswith("/" + sf):
            prefix = joined[:-len(sf)]
            if prefix.endswith("/") and doc_posix.startswith(prefix):
                matches.append(sf)
    return matches[0] if len(matches) == 1 else None


def _match_file_link(cited: str, doc_file: str,
                     source_files: set[str], *,
                     form_mismatch: bool,
                     scan_root: "Path | str | None" = None) -> str | None:
    """Resolve an authored Markdown link to a source file strictly against its target."""
    doc_dir = os.path.dirname(_posix(doc_file))
    relative = _posix(os.path.normpath(os.path.join(doc_dir, _posix(cited))))
    if relative in source_files:
        return relative
    if not form_mismatch:
        return None
    root = _posix(str(scan_root)) if scan_root is not None else None
    if root is None:
        active = _active_scan_root()
        if active is not None:
            root = _posix(str(active))
    if root is not None:
        try:
            rel = _posix(os.path.relpath(relative, root))
        except ValueError:
            return None
        if not rel.startswith("..") and not os.path.isabs(rel) and rel in source_files:
            return rel
        return None
    matches = []
    doc_posix = _posix(doc_file)
    for sf in source_files:
        if relative == sf:
            matches.append(sf)
        elif relative.endswith("/" + sf):
            prefix = relative[:-len(sf)]
            if prefix.endswith("/") and doc_posix.startswith(prefix):
                matches.append(sf)
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
    *,
    scan_root: "Path | str | None" = None,
) -> None:
    """Turn ``language: "markdown"`` raw calls into ``references`` edges in place."""
    mentions = _markdown_raw_calls(per_file)
    if not mentions:
        return

    root = scan_root or _active_scan_root()

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

    def _target(rc: dict) -> tuple[str | None, str, float]:
        """The node a mention resolves to, plus the confidence of that match."""
        names = list(rc.get("qualifiers") or []) + [str(rc.get("callee", "")).strip()]
        cited = rc.get("path")
        if cited:
            source_file = _match_cited_file(
                str(cited), _posix(str(rc.get("source_file", ""))), source_files
            )
            if source_file is None:
                return None, "EXTRACTED", 1.0
            return _resolve_chain(by_file[source_file], names), "EXTRACTED", 1.0
        callee = names[-1]
        if callee in _LANGUAGE_BUILTIN_GLOBALS:
            return None, "INFERRED", 0.95
        qualifiers = set(names[:-1])
        candidates = [
            c for c in by_label.get(callee, [])
            if qualifiers <= _evidence(c, nodes_by_id, parents)
        ]
        return (candidates[0] if len(candidates) == 1 else None), "INFERRED", 0.95

    def _method_owner(node_id: str) -> str | None:
        """The class that owns *node_id*, when it is a method and not a function."""
        for parent in parents.get(node_id, ()):
            node = nodes_by_id.get(parent)
            if node is not None and node.get("_callable_class"):
                return parent
        return None

    def _section_chain(caller: str) -> set[str]:
        """*caller* (a heading or page) plus every heading enclosing it.

        A citation recorded under a heading licenses bare mentions in that
        heading's own section and every section nested inside it; a sibling
        section is not covered (#4804).
        """
        chain = {caller}
        frontier = [caller]
        while frontier:
            nid = frontier.pop()
            for p in parents.get(nid, ()):
                if p not in chain:
                    chain.add(p)
                    frontier.append(p)
        return chain

    #: Targets already cited by each caller (heading or page), used as
    #: section-scoped evidence in passes 2b and 2c.
    cited_targets: dict[str, set[str]] = {}

    # Files cited via file spans, path-qualified mentions, or links (#4804).
    code_file_nodes = {
        _posix(str(n.get("source_file"))): n["id"]
        for n in all_nodes
        if n.get("id") and n.get("file_type") == "code"
        and n.get("source_file") and _is_file_node(n)
    }
    citable_files = set(code_file_nodes)
    # Detect path mixing in partial rebuilds (absolute doc vs relative corpus).
    corpus_has_relative_paths = any(not os.path.isabs(sf) for sf in citable_files)
    cited_files: dict[str, set[str]] = {}
    for rc in mentions:
        cited = rc.get("path")
        if not cited:
            continue
        caller = str(rc.get("evidence_owner") or rc.get("caller_nid", ""))
        if not caller:
            continue
        doc = _posix(str(rc.get("source_file", "")))
        if rc.get("file_link") and not rc.get("wikilink"):
            source_file = _match_file_link(
                str(cited), doc, citable_files,
                form_mismatch=os.path.isabs(doc) and corpus_has_relative_paths,
                scan_root=root,
            )
        else:
            source_file = _match_cited_file_any_form(
                str(cited), doc, citable_files,
                form_mismatch=os.path.isabs(doc) and corpus_has_relative_paths,
                scan_root=root,
            )
        if source_file is not None:
            cited_files.setdefault(caller, set()).add(source_file)

    # Mint page --references--> file edges for links to scanned files (#4804).
    for rc in mentions:
        if not rc.get("file_link"):
            continue
        caller = str(rc.get("caller_nid", ""))
        cited = str(rc.get("path") or "")
        if not caller or caller not in node_ids or not cited:
            continue
        doc = _posix(str(rc.get("source_file", "")))
        if rc.get("wikilink"):
            target_file = _match_cited_file_any_form(
                cited, doc, citable_files,
                form_mismatch=os.path.isabs(doc) and corpus_has_relative_paths,
                scan_root=root,
            )
        else:
            target_file = _match_file_link(
                cited, doc, citable_files,
                form_mismatch=os.path.isabs(doc) and corpus_has_relative_paths,
                scan_root=root,
            )
        target = code_file_nodes.get(target_file) if target_file else None
        if target is None or target == caller or (caller, target) in existing:
            continue
        existing.add((caller, target))
        all_edges.append({
            "source": caller,
            "target": target,
            "relation": "references",
            "context": rc.get("context", ""),
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": rc.get("source_file", ""),
            "source_location": rc.get("source_location"),
            "weight": 1.0,
        })

    def _add(rc: dict, target: str | None, confidence: str, score: float) -> None:
        caller = str(rc.get("caller_nid", ""))
        if target is None or target == caller:
            return
        if (caller, target) in existing:
            # Retain target as section-scoped citation evidence (#4609, #4804).
            cited_targets.setdefault(caller, set()).add(target)
            return
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
        cited_targets.setdefault(caller, set()).add(target)

    # Pass 1: explicit evidence resolves directly (path, dotted chain, or trailing ()).
    bare: list[dict] = []
    for rc in mentions:
        caller = str(rc.get("caller_nid", ""))
        callee = str(rc.get("callee", "")).strip()
        if not caller or not callee or caller not in node_ids:
            continue
        names = list(rc.get("qualifiers") or []) + [callee]
        span = str(rc.get("context") or "")
        if rc.get("path") or len(names) > 1 or "(" in span:
            _add(rc, *_target(rc))
        else:
            bare.append(rc)

    # Pass 2a: classes and distinct identifiers (snake_case, camelCase, export PascalCase).
    method_mentions: list[tuple[dict, str, str, float]] = []
    function_mentions: list[tuple[dict, str, str, float]] = []
    for rc in bare:
        target, confidence, score = _target(rc)
        if target is None:
            continue
        if nodes_by_id.get(target, {}).get("_callable_class"):
            _add(rc, target, confidence, score)
        elif _method_owner(target) is not None:
            method_mentions.append((rc, target, confidence, score))
        else:
            label = _symbol_label(nodes_by_id[target])
            if label[:1].isupper():
                prose_like = not _is_pascal_case_export_language(
                    nodes_by_id[target].get("source_file", ""))
            else:
                prose_like = _is_prose_like_label(label)
            if prose_like:
                function_mentions.append((rc, target, confidence, score))
            else:
                _add(rc, target, confidence, score)

    # Pass 2b: bare method mentions require the owner class to be cited (#4609).
    for rc, target, confidence, score in method_mentions:
        chain = _section_chain(str(rc.get("caller_nid", "")))
        cited = {t for c in chain for t in cited_targets.get(c, ())}
        if _method_owner(target) in cited:
            _add(rc, target, confidence, score)

    # Pass 2c: bare prose-like free function names require defining file or symbol evidence (#4804).
    for rc, target, confidence, score in function_mentions:
        target_file = _posix(str(nodes_by_id.get(target, {}).get("source_file") or ""))
        if not target_file:
            continue
        chain = _section_chain(str(rc.get("caller_nid", "")))
        cited = {t for c in chain for t in cited_targets.get(c, ())}
        if target_file in {f for c in chain for f in cited_files.get(c, ())} or any(
            _posix(str(nodes_by_id.get(t, {}).get("source_file") or "")) == target_file
            for t in cited
        ):
            _add(rc, target, confidence, score)
