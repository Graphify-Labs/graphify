"""Cross-file resolution for Pascal/Delphi calls to inherited methods.

The per-file Pascal/Delphi extractors (``extract_pascal``,
``_extract_pascal_regex``) resolve calls to a method on the caller's own
class, its ancestor chain, or a file-level free function -- but only within
the single file being extracted (each file is extracted independently; see
``_resolve_pascal_callee_factory`` in ``extract.py``). Real Delphi/MTM-style
codebases very commonly split a class across two files -- a code-generator
base class (e.g. Sistec's ``Th0Xxx``) and a manual descendant that extends it
in a separate unit (``Th5Xxx``) -- so a call from the manual descendant to a
method it inherits from the generated base falls outside any one file's own
scope. The per-file pass reports these as ``raw_calls`` instead of guessing.

This resolver runs after all files are extracted (registered in
``graphify.resolver_registry``), with the full merged node/edge corpus
available, so it can walk an ``inherits`` chain across file boundaries. It
intentionally does NOT fall back to a global by-name match the way the
per-file pass's final tier does -- an unqualified call resolving to a
specific ancestor mirrors Delphi's actual method-lookup semantics (nearest
ancestor in the chain), so walking `inherits` is a structurally justified
resolution, not a heuristic guess; guessing by name across an entire
multi-thousand-file corpus is not the same bet.
"""
from __future__ import annotations

_PASCAL_SUFFIXES = (".pas", ".pp", ".dpr", ".dpk", ".inc")


def _pascal_raw_calls(per_file: list[dict]) -> list[dict]:
    calls: list[dict] = []
    for result in per_file:
        if not isinstance(result, dict):
            continue
        for rc in result.get("raw_calls", []):
            if not isinstance(rc, dict):
                continue
            if str(rc.get("source_file", "")).endswith(_PASCAL_SUFFIXES):
                calls.append(rc)
    return calls


def resolve_pascal_inherited_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve Pascal/Delphi calls to a method inherited across file boundaries.

    Purely additive: only emits edges for raw calls the per-file pass could
    not resolve locally (see module docstring). Each emission requires a
    single owning class at the nearest matching level of the caller's
    ``inherits`` chain (god-node guard, same principle as
    ``resolve_ruby_member_calls``) -- an ambiguous or unresolved name
    produces no edge rather than a guess.
    """
    node_by_id = {n.get("id"): n for n in all_nodes}

    class_bases: dict[str, list[str]] = {}
    # method_nid -> its owning class nid, so a raw call's caller_nid (a method
    # or free-function nid) can be mapped to the CLASS whose inherits chain
    # should be walked. Derived from `all_edges` (already remapped/finalized
    # by the id-disambiguation passes that run before resolvers, same as
    # caller_nid itself) rather than carried as a separate field on the raw
    # call -- a field the generic id-remap machinery would not know to update.
    owner_of: dict[str, str] = {}
    class_procs: dict[str, dict[str, list[str]]] = {}
    for e in all_edges:
        if e.get("relation") == "inherits":
            class_bases.setdefault(e["source"], []).append(e["target"])
        elif e.get("relation") == "method":
            owner, method_nid = e.get("source"), e.get("target")
            owner_of[method_nid] = owner
            mnode = node_by_id.get(method_nid)
            if mnode is None:
                continue
            name_lower = str(mnode.get("label", "")).removesuffix("()").lower()
            # Count DISTINCT methods, not edge multiplicity: the tree-sitter
            # Pascal extractor emits one `method` edge for the interface
            # declaration and one for the implementation, so the same
            # method_nid arrives twice. Deduping keeps the single-owner
            # god-node guard below (`len(candidates) == 1`) measuring real
            # same-name collisions across classes, not the same method
            # double-counted -- otherwise every inherited call looks ambiguous.
            bucket = class_procs.setdefault(owner, {}).setdefault(name_lower, [])
            if method_nid not in bucket:
                bucket.append(method_nid)

    existing_pairs = {(e.get("source"), e.get("target")) for e in all_edges}

    def _resolve(owner: str, name_lower: str) -> str | None:
        seen_bases: set[str] = set()
        queue = list(class_bases.get(owner, []))
        while queue:
            base = queue.pop(0)
            if base in seen_bases:
                continue
            seen_bases.add(base)
            candidates = class_procs.get(base, {}).get(name_lower)
            if candidates:
                return candidates[0] if len(candidates) == 1 else None
            queue.extend(class_bases.get(base, []))
        return None

    for rc in _pascal_raw_calls(per_file):
        caller = rc.get("caller_nid")
        name_lower = rc.get("callee")
        if not caller or not name_lower:
            continue
        owner = owner_of.get(caller)
        if not owner:
            continue
        target = _resolve(str(owner), str(name_lower))
        if not target or target == caller:
            continue
        pair = (caller, target)
        if pair in existing_pairs:
            continue
        existing_pairs.add(pair)
        all_edges.append({
            "source": caller,
            "target": target,
            "relation": "calls",
            "context": "call",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": rc.get("source_file", ""),
            "source_location": rc.get("source_location"),
            "weight": 1.0,
        })
