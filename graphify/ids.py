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
replace runs of non-word characters with a single underscore (``re.UNICODE`` so
CJK/Cyrillic/Arabic/accented-Latin letters survive instead of collapsing to a
per-file node), collapse repeated underscores, strip leading/trailing
underscores, and casefold.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

__all__ = ["normalize_id", "make_id", "file_stem"]


def normalize_id(s: str) -> str:
    r"""Normalize a single ID string to its canonical form.

    Idempotent: ``normalize_id(normalize_id(s)) == normalize_id(s)``.
    """
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[^\w]+", "_", s, flags=re.UNICODE)
    s = re.sub(r"_+", "_", s)
    return s.strip("_").casefold()


def make_id(*parts: str) -> str:
    """Build a canonical node ID from one or more name parts.

    Parts are joined with ``_`` (after stripping stray ``_``/``.`` edges from each
    part) and then run through :func:`normalize_id`, so the result is identical to
    what the builder produces from the joined string.
    """
    return normalize_id("_".join(p.strip("_.") for p in parts if p))


def file_stem(path: str | Path, repo_root: str | Path | None = None) -> str:
    """Build the canonical file-stem prefix for path-derived node IDs.

    When ``repo_root`` is available, the stem is based on the full path relative
    to that root. Relative paths are treated as already repo-relative. Absolute
    paths without a root keep the historical one-parent fallback so extractors
    can still be remapped after the scan root is known.
    """
    path = Path(path)
    relative_path: Path | None = None
    if repo_root is not None:
        try:
            relative_path = path.resolve().relative_to(Path(repo_root).resolve())
        except ValueError:
            relative_path = None
    elif not path.is_absolute():
        relative_path = path

    if relative_path is not None:
        return ".".join(relative_path.with_suffix("").parts)

    parent = path.parent.name
    if parent and parent not in (".", ""):
        return f"{parent}.{path.stem}"
    return path.stem
