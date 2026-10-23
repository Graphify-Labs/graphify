"""Cross-file resolution for Common Lisp calls by bare name.

The per-file Common Lisp extractor (``extract_commonlisp``) resolves a call
only against the definitions in the file being parsed, because each file is
extracted independently. A Common Lisp system spreads its functions across
many files of one package and calls them by bare name with no receiver and no
import statement at the call site, so the per-file pass resolves a minority of
the real calls and the rest have no candidate to bind to. Those are reported
as ``raw_calls`` rather than guessed at.

This resolver runs after all files are extracted (registered in
``graphify.resolver_registry``) with the full merged corpus available, so a
bare name can be matched against every definition the corpus knows. Modelled
on ``pascal_resolution`` -- same shape of problem, a call whose target is
structurally outside any one file's scope -- but the resolution rule differs
because the languages differ. Pascal walks an ``inherits`` chain, mirroring
Delphi's method lookup. Common Lisp has no receiver to type and no chain to
walk: a bare name in a package denotes one function, so the corpus-wide name
is the resolution, guarded by requiring a single candidate.

Calls into the standard library and into systems outside the scan need no
special handling and get none: nothing in the corpus defines ``car`` or
``format``, so they match no candidate and produce no edge. That falls out of
matching against definitions rather than against a name list, which is also
why no such list is maintained here.
"""
from __future__ import annotations

from .paths import disambiguate_ambiguous_candidates
from .symbol_resolution import (
    build_label_index,
    existing_edge_pairs,
    iter_raw_calls,
)

_COMMONLISP_SUFFIXES = (".lisp", ".cl", ".lsp", ".asd")


def resolve_commonlisp_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve Common Lisp calls whose target is defined in another file.

    Purely additive: emits edges only for raw calls the per-file pass could not
    resolve locally. A name matching more than one definition goes through the
    shared tie-breakers and is dropped unless exactly one survives, so an
    ambiguous name produces no edge rather than a guess.
    """
    label_index = build_label_index(all_nodes)
    known = existing_edge_pairs(all_edges)
    nid_to_source_file = {
        str(n.get("id")): str(n.get("source_file", ""))
        for n in all_nodes
        if n.get("id")
    }

    for rc in iter_raw_calls(per_file):
        # raw_calls is shared by every language, so claim only our own.
        if rc.get("lang") != "commonlisp":
            continue
        if not str(rc.get("source_file", "")).endswith(_COMMONLISP_SUFFIXES):
            continue
        callee = str(rc.get("callee", "")).strip()
        caller = str(rc.get("caller_nid", ""))
        if not callee or not caller:
            continue
        candidates = label_index.get(callee.lower(), [])
        if not candidates:
            continue
        if len(candidates) == 1:
            target: str | None = candidates[0]
        else:
            target = disambiguate_ambiguous_candidates(
                candidates,
                {c: nid_to_source_file.get(c, "") for c in candidates},
                str(rc.get("source_file", "")),
            )
            if target is None:
                continue
        if target == caller:
            continue
        triple = (caller, target, "calls")
        if triple in known:
            continue
        known.add(triple)
        all_edges.append({
            "source": caller,
            "target": target,
            "relation": "calls",
            "context": "call",
            # INFERRED, matching the shared bare-name resolver: a name match
            # across the corpus is weaker evidence than a call the extractor
            # resolved inside one file.
            "confidence": "INFERRED",
            "confidence_score": 0.85,
            "source_file": rc.get("source_file", ""),
            "source_location": rc.get("source_location"),
            "weight": 1.0,
        })
