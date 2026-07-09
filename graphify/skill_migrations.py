"""Skill version reconciliation — detect installed-vs-package drift and name the
migrations needed to close it.

graphify ships its agent instructions as a *skill* (SKILL.md + references/) that
is copied into each platform's skill dir at ``graphify install`` time, with a
``.graphify_version`` stamp beside it. Nothing keeps that copy in lockstep with
the installed Python package afterwards, so the two drift — e.g. a skill stamped
0.9.2 sitting next to a 0.9.0 package. ``graphify skill check-update`` surfaces
that drift; this module holds the version math and the migration registry that
explains what a given jump entails.

A ``Migration`` records a version whose skill format changed and how to adopt it
(almost always: re-run ``graphify install``, which re-renders the skill + sidecar
from the packaged artifacts). Append an entry here whenever the skill's on-disk
contract changes so ``check-update`` can tell users *why* a re-install matters,
not just that versions differ.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Migration:
    version: str  # the package version that introduced the skill change
    summary: str  # what changed in the on-disk skill contract
    action: str = "reinstall"  # how to adopt it


# Oldest -> newest. Keep sorted by version.
MIGRATIONS: list[Migration] = [
    Migration(
        "0.9.0",
        "Baseline progressive skill: SKILL.md + references/ sidecar with the "
        "graphify-query-first workflow.",
        "reinstall",
    ),
]


def parse_version(value: str) -> tuple[int, ...]:
    """Lenient dotted-numeric parse. Non-numeric or 'unknown' -> (0,).

    Only the leading digit run of each dotted segment is read, so pre-release
    tags ('1.2.0rc1') compare by their numeric core without raising.
    """
    if not value or value == "unknown":
        return (0,)
    parts: list[int] = []
    for segment in str(value).split("."):
        digits = ""
        for ch in segment:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def compare_versions(a: str, b: str) -> int:
    """-1 if a<b, 0 if equal, 1 if a>b (by parsed numeric tuple)."""
    pa, pb = parse_version(a), parse_version(b)
    # Pad to equal length so (0,9) and (0,9,0) compare equal.
    width = max(len(pa), len(pb))
    pa += (0,) * (width - len(pa))
    pb += (0,) * (width - len(pb))
    return (pa > pb) - (pa < pb)


def applicable_migrations(installed: str, target: str) -> list[Migration]:
    """Migrations introduced after `installed` and up to (including) `target`.

    Empty when the skill is up to date or ahead of the package (a downgrade —
    ``check-update`` reports that separately; there is nothing to migrate *to*).
    """
    return [
        m
        for m in MIGRATIONS
        if compare_versions(m.version, installed) > 0
        and compare_versions(m.version, target) <= 0
    ]


def drift_state(installed: str, package: str) -> str:
    """Classify the relationship: 'current' | 'behind' | 'ahead'."""
    cmp = compare_versions(installed, package)
    if cmp == 0:
        return "current"
    return "behind" if cmp < 0 else "ahead"
