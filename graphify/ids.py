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

The recipe: NFKC-normalize (so composed/decomposed Unicode forms collapse),
casefold, NFKC-normalize again (casefold can *expand* a character into a base
letter plus a combining mark — ``İ`` -> ``i`` + U+0307 — and the second pass
recomposes what can be recomposed), replace runs of non-word characters with a
single underscore (``re.UNICODE`` so CJK/Cyrillic/Arabic/accented-Latin letters
survive instead of collapsing to a per-file node), collapse repeated
underscores, then strip leading/trailing underscores.

Casefolding runs BEFORE the non-word filter, not after. With it last, the
combining marks casefold introduces were never filtered: ``İslemYap`` produced
``i̇slemyap`` — an id containing U+0307, which is not a ``\\w`` character — and a
second pass collapsed it to ``i_slemyap``, so the function was not idempotent
and the builder's re-normalization disagreed with the extractor's ``make_id``
for any Turkish identifier (#2614).
"""
from __future__ import annotations

import re
import unicodedata

__all__ = ["normalize_id", "make_id"]


def normalize_id(s: str) -> str:
    r"""Normalize a single ID string to its canonical form.

    Guarantees, both enforced by tests:

    - Idempotent: ``normalize_id(normalize_id(s)) == normalize_id(s)``.
    - The result contains only ``\w`` characters and ``_``.

    Casefolding before the ``[^\w]+`` filter is what makes both hold — see the
    module docstring for why the reverse order silently broke them (#2614).
    """
    s = unicodedata.normalize("NFKC", s)
    # casefold can expand one character into a letter + combining mark, so it
    # must run while the non-word filter can still see the result.
    s = unicodedata.normalize("NFKC", s.casefold())
    s = re.sub(r"[^\w]+", "_", s, flags=re.UNICODE)
    s = re.sub(r"_+", "_", s)
    return s.strip("_")


def make_id(*parts: str) -> str:
    """Build a canonical node ID from one or more name parts.

    Parts are joined with ``_`` (after stripping stray ``_``/``.`` edges from each
    part) and then run through :func:`normalize_id`, so the result is identical to
    what the builder produces from the joined string.
    """
    return normalize_id("_".join(p.strip("_.") for p in parts if p))
