"""Single source of truth for the issue-triage label taxonomy.

Everything the triage bot may create or apply is defined here. The classifier in
``tools.triage.classify`` builds its model allowlist from these tuples, and
``tools.triage.sync_labels`` creates them on the repository, so the labels the
model is told about and the labels that exist cannot drift. Python (not YAML) so
the workflow needs no YAML dependency and there is exactly one source.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Label:
    """One repository label: name, 6-hex colour, and a short description."""

    name: str
    color: str
    description: str


# area/ -- WHERE in the codebase the work lands. The model picks one, or two
# only when the issue is clearly split across two areas.
AREAS: tuple[Label, ...] = (
    Label("area/extract", "1d76db", "Source extraction: languages, parsers, files to nodes/edges"),
    Label("area/build", "1d76db", "Graph construction, merge, dedupe, ids, pruning"),
    Label("area/analyze", "1d76db", "Communities, god nodes, report, cycles, surprising edges"),
    Label("area/query", "1d76db", "query, path, explain, affected, serve"),
    Label("area/export", "1d76db", "HTML, Obsidian, GraphDB, call-flow, Neo4j/FalkorDB exports"),
    Label("area/cli", "1d76db", "Command-line interface, flags, dispatch, help text"),
    Label("area/install", "1d76db", "Platform install/uninstall, skills, hooks, MCP, plugins"),
    Label("area/watch", "1d76db", "Incremental updates, file watching, git hooks"),
    Label("area/llm", "1d76db", "Semantic extraction and LLM backends/providers"),
    Label("area/ci", "1d76db", "GitHub Actions, release, packaging"),
    Label("area/docs", "1d76db", "Documentation and guides"),
    Label("area/other", "d4c5f9", "None of the other areas"),
)

# kind/ -- WHAT the issue is. The model picks exactly one.
KINDS: tuple[Label, ...] = (
    Label("kind/bug", "d73a4a", "Something is not working as documented"),
    Label("kind/feature", "a2eeef", "New capability or enhancement"),
    Label("kind/docs", "0075ca", "Documentation change"),
    Label("kind/question", "d876e3", "Question or support request"),
    Label("kind/refactor", "fbca04", "Internal cleanup, no behaviour change"),
    Label("kind/performance", "c2e0c6", "Speed or memory improvement"),
    Label("kind/other", "ededed", "Anything else"),
)

# status/ -- workflow state. Never chosen by the model.
STATUS: tuple[Label, ...] = (
    Label("status/need-triage", "fbca04", "Opened, not yet triaged by a maintainer or the bot"),
    Label("status/bot-triaged", "0e8a16", "area/ and kind/ were set by the triage bot"),
    Label("status/gfi-suggested", "7057ff", "The bot suggested this as a good first issue"),
)

# The explicit allowlists the model must choose from. Anything outside is dropped.
MODEL_SELECTABLE_AREA: frozenset[str] = frozenset(label.name for label in AREAS)
MODEL_SELECTABLE_KIND: frozenset[str] = frozenset(label.name for label in KINDS)

# Status label names, so the workflow files can be checked against taxonomy for
# drift (a rename here that the workflow still uses by the old name would create a
# second, invisible source of truth).
STATUS_NAMES: frozenset[str] = frozenset(label.name for label in STATUS)

# The human-facing definition used verbatim in the prompt. Deliberately strict:
# a wrong ``good first issue`` is worse than none, so the bot only *suggests* and
# a maintainer confirms.
GFI_DEFINITION: str = (
    "A good first issue is a self-contained change in a single file or one small "
    "area, in one language, with a clear reproduction or acceptance criteria, that "
    "does NOT touch the graph format, caches, provenance, incremental/watch state, "
    "or any documented invariant. A newcomer should be able to finish it without "
    "deep repository knowledge. When in doubt, answer false."
)


def all_managed_labels() -> tuple[Label, ...]:
    """Every label the sync step creates: areas, kinds, and statuses."""
    return AREAS + KINDS + STATUS
