"""Expand incremental work to already admitted owners of changed physical bytes.

Detection, exclusions, deletion handling, extraction and publication remain with
the watch caller. This boundary reads only filesystem identity, never source
content, and retains no cache or mutable state after one selection operation.
"""
from __future__ import annotations

from collections.abc import Iterable
import json
import os
from pathlib import Path
import stat


SOURCE_CONTEXT_LIMIT = 160


def _safe_source(path: Path, root: Path) -> str:
    """A failed identity lookup cannot justify resolving a diagnostic path again."""
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        return ""
    if len(relative) > SOURCE_CONTEXT_LIMIT or any(
            ord(char) < 32 or 127 <= ord(char) < 160 or char in "\u2028\u2029"
            for char in relative):
        return ""
    return relative


def physical_identity(path: Path, root: Path) -> tuple:
    """Verify a regular contained input before comparing shared physical content."""
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
        value = path.stat()
        if not stat.S_ISREG(value.st_mode):
            raise ValueError("not a regular admitted source")
        if value.st_dev and value.st_ino:
            return "inode", value.st_dev, value.st_ino
        # Some filesystems do not expose inode identity. A canonical path still
        # proves symlink/junction co-ownership without guessing about hardlinks.
        return "path", resolved
    except (OSError, RuntimeError, ValueError):
        source = json.dumps(_safe_source(path, root), ensure_ascii=True)
        raise ValueError(f"WATCH_SOURCE_IDENTITY_FAILED: source={source}; admitted source "
                         "identity unavailable; prior products retained; repair and retry") from None


def expand_changed_coowners(wanted: Iterable[Path], corpus: Iterable[Path], *, root: Path) -> list[Path]:
    """Append verified co-owners without authorizing discovery or deleted inputs.

    The caller supplies only positive, admitted, nonsemantic source paths. Keep
    notification order and append additional owners in accepted corpus order.
    A failed lookup refuses partial work so publication can retain its cohort.
    """
    wanted = list(wanted)
    if not wanted:
        return wanted
    accepted = {Path(os.path.abspath(path)): Path(path) for path in corpus}
    changed = {Path(os.path.abspath(path)) for path in wanted}
    if not changed <= accepted.keys():
        raise ValueError("WATCH_SOURCE_IDENTITY_FAILED: source=\"\"; changed source is not "
                         "admitted; prior products retained; repair and retry")
    identities = {path: physical_identity(path, root) for path in accepted}
    affected = {identities[path] for path in changed}
    return wanted + [original for path, original in accepted.items()
                     if path not in changed and identities[path] in affected]
