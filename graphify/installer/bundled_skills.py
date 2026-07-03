"""Registry of skills bundled with graphify for offline installation.

Each entry is a host-agnostic SKILL.md (plus optional references/) that
`copy_bundled_skills()` writes into `<host_skill_dir>/<name>/` on the
user's machine. Always-overwrite semantics: existing files are replaced
unconditionally. The `gf-` namespace prefix guarantees no collision with
user-installed plugins (e.g. the upstream superpowers plugin uses bare
names like `brainstorming`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BundledSkill:
    """A skill bundled with graphify.

    Attributes:
        name: Final install name (always `gf-` prefixed). Also the directory
            name created under the host's `skills/` parent.
        source_subpath: Path relative to the graphify package root where the
            SKILL.md file lives (e.g.
            `bundled_skills/superpowers/brainstorming/SKILL.md`).
        has_references: True if a `references/` sidecar should be copied
            alongside SKILL.md. Only `gf-llm-wiki` uses this today.
    """

    name: str
    source_subpath: str
    has_references: bool


_BUNDLED: tuple[BundledSkill, ...] = (
    # 14 superpowers skills (MIT, Jesse Vincent) — see ./superpowers/LICENSE
    BundledSkill("gf-brainstorming",                  "bundled_skills/superpowers/brainstorming/SKILL.md",                  False),
    BundledSkill("gf-writing-plans",                  "bundled_skills/superpowers/writing-plans/SKILL.md",                  False),
    BundledSkill("gf-subagent-driven-development",    "bundled_skills/superpowers/subagent-driven-development/SKILL.md",    False),
    BundledSkill("gf-test-driven-development",        "bundled_skills/superpowers/test-driven-development/SKILL.md",        False),
    BundledSkill("gf-systematic-debugging",           "bundled_skills/superpowers/systematic-debugging/SKILL.md",           False),
    BundledSkill("gf-using-git-worktrees",            "bundled_skills/superpowers/using-git-worktrees/SKILL.md",            False),
    BundledSkill("gf-requesting-code-review",         "bundled_skills/superpowers/requesting-code-review/SKILL.md",         False),
    BundledSkill("gf-receiving-code-review",          "bundled_skills/superpowers/receiving-code-review/SKILL.md",          False),
    BundledSkill("gf-executing-plans",                "bundled_skills/superpowers/executing-plans/SKILL.md",                False),
    BundledSkill("gf-finishing-a-development-branch", "bundled_skills/superpowers/finishing-a-development-branch/SKILL.md", False),
    BundledSkill("gf-dispatching-parallel-agents",    "bundled_skills/superpowers/dispatching-parallel-agents/SKILL.md",    False),
    BundledSkill("gf-using-superpowers",              "bundled_skills/superpowers/using-superpowers/SKILL.md",              False),
    BundledSkill("gf-verification-before-completion", "bundled_skills/superpowers/verification-before-completion/SKILL.md", False),
    BundledSkill("gf-writing-skills",                 "bundled_skills/superpowers/writing-skills/SKILL.md",                 False),
    # llm-wiki (project-local) — see ./llm-wiki/LICENSE
    BundledSkill("gf-llm-wiki",                       "bundled_skills/llm-wiki/SKILL.md",                                   True),
    # code-pipeline (project-local) — feature-lifecycle orchestrator
    BundledSkill("code-pipeline",                  "bundled_skills/code-pipeline/SKILL.md",                              False),
)


# Hosts that don't accept a plain SKILL.md — they need format adapters
# (.mdc for cursor, GEMINI.md injection for gemini). v2 work; skipped for now.
_UNSUPPORTED_HOSTS = frozenset({"cursor", "gemini"})


def all_bundled() -> tuple[BundledSkill, ...]:
    """Return the full tuple of bundled skills."""
    return _BUNDLED


def supports_host(host_name: str) -> bool:
    """True if bundled skills can be installed for this host."""
    return host_name not in _UNSUPPORTED_HOSTS


def bundled_skill_dir(host, skill_name: str, *, root: Path) -> Path:
    """Target directory for installing `skill_name` on `host`.

    Formula: `root/<host.marker>/<up-to-skills>/<skill_name>/`.

    Replaces the trailing `graphify` segment of `host.skill_subpath` with
    `skill_name`. Falls back to `root/<host.marker>/skills/<skill_name>/`
    if the host's subpath doesn't end in `graphify` (defensive — no current
    host falls through, but `cursor`'s `rules/` subpath does, and we skip
    cursor entirely via `supports_host`).

    Worked examples:
        claude:     ~/.claude/skills/gf-brainstorming/
        codex:      ~/.codex/skills/gf-brainstorming/
        aider:      ~/.aider/gf-brainstorming/         (no skills/ parent)
        pi:         ~/.pi/agent/skills/gf-brainstorming/  (extra agent/ prefix)
        mobilecoder: ~/.mobilecoder/skills/gf-brainstorming/
    """
    parts = host.skill_subpath.parts
    if parts and parts[-1] == "graphify":
        new_subpath = Path(*parts[:-1]) / skill_name
    else:
        new_subpath = Path("skills") / skill_name
    return root / host.marker / new_subpath