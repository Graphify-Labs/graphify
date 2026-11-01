"""Caller-owned conservative C# refresh over an already admitted corpus.

Partial-type canonical IDs and inherited field ownership span files/assemblies.
Until dependency-directed invalidation is characterized, source or project/input
profile changes refresh the live C# cohort; warm syntax caches remain reusable.
This helper never discovers files or reparses borrowed resolver context.
"""
from __future__ import annotations

from pathlib import Path

from graphify.rcfile import effective_suffix


_INPUTS = {".cs", ".csproj", ".fsproj", ".vbproj", ".sln", ".slnx"}


def refresh_csharp_paths(changed, admitted, *, removed=(), profile_changed=False):
    """Extend actual changed paths with actual admitted C# sources when needed."""
    selected = [Path(path) for path in changed]
    cohort = [Path(path) for path in admitted if effective_suffix(path).lower() == ".cs"]
    if not cohort:
        return selected
    relevant = profile_changed or any(effective_suffix(path).lower() in _INPUTS for path in [*selected, *removed])
    if not relevant:
        return selected
    seen = {str(path) for path in selected}
    selected.extend(path for path in cohort if str(path) not in seen)
    return selected
