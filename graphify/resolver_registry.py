"""Registry for cross-file, language-specific resolution passes.

Some call/reference edges can only be resolved with language-specific knowledge
(receiver typing, qualified member calls, framework conventions). Historically
these ran as a hand-wired sequence of suffix-gated
``if <lang>_paths: try: _resolve_<lang>(...)`` blocks at the tail of
``extract.extract()``. That pattern is the de-facto extension point for
per-language resolution; this module formalizes it so a new language plugs in by
registering one ``LanguageResolver`` instead of editing ``extract()``'s body.

This module deliberately knows nothing about any specific language — languages
register themselves (see ``extract.py``), keeping the dependency direction one
way (``extract`` → ``resolver_registry``) and this seam small and reviewable on
its own, separate from the multi-thousand-line ``extract`` module.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class LanguageResolver:
    """One cross-file, language-specific resolution pass.

    ``resolve`` has the signature ``(per_file, all_nodes, all_edges) -> None`` and
    mutates ``all_nodes`` / ``all_edges`` in place, matching the existing
    member-call resolvers. ``suffixes`` gates activation: the pass runs only when
    the corpus contains at least one file with one of these extensions.
    """

    name: str
    suffixes: frozenset
    resolve: Callable


# Module-level registry, populated by callers via register(). Ordered: resolvers
# run in registration order, preserving any required sequencing between passes.
_REGISTRY: list[LanguageResolver] = []


def register(resolver: LanguageResolver) -> LanguageResolver:
    """Append a resolver to the global registry and return it (for inline use)."""
    _REGISTRY.append(resolver)
    return resolver


def registered_resolvers() -> list[LanguageResolver]:
    """Return a copy of the registered resolvers, in registration order."""
    return list(_REGISTRY)


def run_language_resolvers(
    paths: Sequence[Path],
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
    *,
    resolvers: Sequence[LanguageResolver] | None = None,
) -> None:
    """Run every resolver whose suffix appears in ``paths``.

    Behaviorally identical to the prior hand-wired sequence of suffix-gated,
    try/except-wrapped passes: same activation rule (suffix present), same
    failure handling (log a warning and continue to the next pass), same
    execution order (registration order).

    ``resolvers`` defaults to the global registry; tests pass an explicit list to
    exercise the driver in isolation.
    """
    active = _REGISTRY if resolvers is None else resolvers
    suffixes_present = {p.suffix for p in paths}
    for resolver in active:
        if not (resolver.suffixes & suffixes_present):
            continue
        try:
            resolver.resolve(per_file, all_nodes, all_edges)
        except Exception as exc:
            _LOG.warning("%s resolution failed, skipping: %s", resolver.name, exc)
