"""Single source of truth for node-ID normalization.

Three independent producers must agree on node IDs or the graph splits a single
entity into disconnected ghost nodes:

1. The AST extractor (``extract._make_id``) — deterministic, per-language.
2. The semantic subagents (LLM) — follow the node-ID spec in the skill prompt.
3. The graph builder (``build._normalize_id``) — reconciles edge endpoints when
   the LLM emits IDs with slightly different punctuation or casing than the AST.

Historically the normalization recipe was copy-pasted into ``extract._make_id``
and ``build._normalize_id`` and kept in sync only by mirrored docstrings, which
is exactly how the recurring ID-drift bug class crept in (#811 Unicode collapse,
#550 same-filename collisions, #1033 AST-vs-LLM file-node mismatch, #1104). This
module exists so the recipe lives in one place and the two callers can no longer
diverge.

The recipe: iterate ``casefold`` then NFKC-normalize to a fixpoint (casefold can
*expand* a character into a base letter plus a combining mark — ``İ`` -> ``i`` +
U+0307 — and NFKC then recomposes what can be recomposed; because the two do not
commute and neither is a fixpoint of the other, a single pass is not
caseless-stable), then replace runs of non-word characters with a single
underscore (``re.UNICODE`` so CJK/Cyrillic/Arabic/accented-Latin letters survive
instead of collapsing to a per-file node), collapse repeated underscores, then
strip leading/trailing underscores.

Casefolding runs BEFORE the non-word filter, not after. With it last, the
combining marks casefold introduces were never filtered: ``İslemYap`` produced
``i̇slemyap`` — an id containing U+0307, which is not a ``\\w`` character — and a
second pass collapsed it to ``i_slemyap``, so the function was not idempotent
and the builder's re-normalization disagreed with the extractor's ``make_id``
for any Turkish identifier (#2614).

Casefolding runs in a FIXPOINT LOOP, not once. A single ``NFKC(casefold(...))``
left ``normalize_id(s) != normalize_id(s.casefold())`` for some combining-mark
sequences (Greek ypogegrammeni U+0345 followed by a combining accent):
pre-casefolding turns U+0345 into ``ι``, which NFKC composes with the accent into
a precomposed char the single pass never reached. Iterating to a fixpoint —
casefold first, on the raw input — makes the result caseless-stable regardless of
how many times the caller has already casefolded.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

__all__ = ["normalize_id", "make_id", "decl_salt", "DeclIdRegistry"]


def normalize_id(s: str) -> str:
    r"""Normalize a single ID string to its canonical form.

    Guarantees, all enforced by tests:

    - Idempotent: ``normalize_id(normalize_id(s)) == normalize_id(s)``.
    - The result contains only ``\w`` characters and ``_``.
    - Caseless-stable: ``normalize_id(s) == normalize_id(s.casefold())``.

    casefold and NFKC do not commute, and neither is a fixpoint of the other:
    casefolding a char can expand it into a base letter plus a combining mark
    (``İ`` -> ``i`` + U+0307), and NFKC can then recompose that mark with an
    adjacent one into a different precomposed char. A single ``NFKC(casefold(...))``
    pass therefore left ``normalize_id(s) != normalize_id(s.casefold())`` for some
    combining-mark sequences (e.g. Greek ypogegrammeni U+0345 followed by a
    combining accent): pre-casefolding turned U+0345 into ``ι`` which NFKC then
    composed with the accent, reaching a form the single-pass recipe never saw.

    So iterate ``casefold`` then ``NFKC`` to a fixpoint (casefold FIRST, on the
    raw input, so a caller that pre-casefolds lands on the same fixpoint). The
    loop is bounded — Unicode caseless folding converges in one or two steps —
    with a hard cap as a termination guard. Only then apply the ``[^\w]+`` filter,
    so every combining mark casefold introduced has been fully normalized before
    it is filtered (#2614 and its combining-mark follow-on).
    """
    cur = s
    for _ in range(6):
        nxt = unicodedata.normalize("NFKC", cur.casefold())
        if nxt == cur:
            break
        cur = nxt
    cur = re.sub(r"[^\w]+", "_", cur, flags=re.UNICODE)
    cur = re.sub(r"_+", "_", cur)
    return cur.strip("_")


def decl_salt(name: str) -> str:
    """Stable 12-hex digest appended when a declaration id collides (#4854)."""
    return hashlib.sha1(
        name.encode("utf-8", "replace"), usedforsecurity=False
    ).hexdigest()[:12]


class DeclIdRegistry:
    """Assign unique ids to declarations in one file.

    Ownership is keyed by the id the declaration would have used, so two
    declarations whose names normalize alike (``Foo`` / ``_Foo``, or ``Base`` in
    two namespaces) stay distinct. A reference lookup by name only answers when
    exactly one declaration in the file spells that name; an ambiguous name
    keeps the caller's existing fallback.
    """

    def __init__(self, reserved_ids=()):
        self._assigned: dict[tuple[str, str], str] = {}
        self._owners: dict[str, tuple[str, str]] = {
            rid: ("file", rid) for rid in reserved_ids
        }
        self._by_name: dict[tuple[str, str], set[str]] = {}
        self._salted: set[str] = set()

    def resolve(self, nid: str, name: str, kind: str, taken) -> str:
        key = (kind, nid)
        owner = self._owners.get(nid)
        if owner == key:
            return self._assigned[key]
        if nid not in taken and owner is None:
            self._owners[nid] = key
            self._assigned[key] = nid
            self._by_name.setdefault((kind, normalize_id(name)), set()).add(nid)
            return nid
        assigned = self._assigned.get(key)
        if assigned is not None:
            return assigned
        # An id already used by a real declaration is a duplicate reference to
        # that declaration (prototype owner, same name re-declared); reuse it
        # instead of minting a second node. Only a salted id, whose owner stole
        # the spelling from this declaration, forces a counter-salt (#4854).
        if (nid in taken and owner is not None and owner[0] != "file"
                and nid not in self._salted):
            return nid
        base = make_id(nid, decl_salt(name))
        candidate = base
        counter = 2
        while candidate in taken or candidate in self._owners:
            candidate = make_id(base, str(counter))
            counter += 1
        self._owners[candidate] = key
        self._assigned[key] = candidate
        self._salted.add(candidate)
        self._by_name.setdefault((kind, normalize_id(name)), set()).add(candidate)
        return candidate

    def lookup(self, name: str, kinds=("type", "fn", "var", "ns", "alias")) -> str | None:
        norm = normalize_id(name)
        for kind in kinds:
            ids = self._by_name.get((kind, norm))
            if ids:
                return next(iter(ids)) if len(ids) == 1 else None
        return None


def make_id(*parts: str) -> str:
    """Build a canonical node ID from one or more name parts.

    Parts are joined with ``_`` (after stripping stray ``_``/``.`` edges from each
    part) and then run through :func:`normalize_id`, so the result is identical to
    what the builder produces from the joined string.
    """
    return normalize_id("_".join(p.strip("_.") for p in parts if p))
