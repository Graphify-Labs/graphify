"""Keep incremental work within admitted canonical filename collision cohorts.

The caller owns discovery, physical containment, semantic exclusions and output.
This pure selector preserves walked spellings; it reads no source or filesystem
identity and never reconstructs graph roles from persisted labels or node IDs.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id


_FAILURE = ('WATCH_SOURCE_IDENTITY_FAILED: source=""; filename cohort selection '
            'is not admitted; prior products retained; repair and retry')


def expand_filename_cohorts(selected: Iterable[Path], accepted: Iterable[Path], *,
                            root: Path, retired: Iterable[Path] = ()) -> list[Path]:
    """Append only admitted peers whose canonical file-node identity can collide.

    All inputs are absolute walked names already admitted by the caller. Keep
    existing selection order and append new peers in lexical relative order.
    Retired names are caller-recorded deletion identities: they select surviving
    peers without authorizing a read or publication of the absent source.
    Matching uses the generic producer's canonical file key; physical co-owner
    expansion remains the caller's independent responsibility.
    """
    root = Path(root)
    if not root.is_absolute() or ".." in root.parts:
        raise ValueError(_FAILURE)

    def relative(path):
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError(_FAILURE)
        try:
            result = path.relative_to(root)
        except ValueError:
            raise ValueError(_FAILURE) from None
        if not result.name:
            raise ValueError(_FAILURE)
        return result

    # Validate the complete admitted snapshot before selecting any partial work.
    sources = {Path(path): relative(Path(path)) for path in accepted}
    wanted = list(dict.fromkeys(Path(path) for path in selected))
    if not set(wanted) <= sources.keys():
        raise ValueError(_FAILURE)
    keys = {path: _make_id(_file_stem(name)) for path, name in sources.items()}
    affected = {keys[path] for path in wanted}
    affected.update(_make_id(_file_stem(relative(Path(path)))) for path in retired)
    changed = set(wanted)
    return wanted + sorted((path for path in sources if path not in changed
                            and keys[path] in affected),
                           key=lambda path: sources[path].as_posix())
