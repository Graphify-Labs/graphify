"""Stateless source spelling, walked naming, and shared physical ID ownership.

Native input spelling is admitted before extraction. After physical containment,
walked aliases retain their lexical owner, and shared resolved forms receive an
explicit owner without relying on batch order. The caller owns admission scope,
the per-run realpath cache, source reads, endpoint creation, and publication.
"""
from __future__ import annotations

from collections.abc import Callable
import ctypes
import json
import os
from pathlib import Path
import stat


NATIVE_PATH_CAPACITY = 32768
SOURCE_CONTEXT_LIMIT = 160


def _source_context(path: Path, root: Path | None) -> str:
    """Use only lexical context; failed admission cannot authorize another lookup."""
    if root is None:
        return ""
    try:
        relative = Path(os.path.abspath(path)).relative_to(Path(os.path.abspath(root))).as_posix()
    except (OSError, RuntimeError, ValueError):
        return ""
    if len(relative) > SOURCE_CONTEXT_LIMIT or any(
            ord(char) < 32 or 127 <= ord(char) < 160 or char in "\u2028\u2029"
            for char in relative):
        return ""
    return relative


def _native_long_name(path: Path) -> str:
    """Expand NTFS entry spellings without resolving lexical junction owners."""
    api = ctypes.windll.kernel32.GetLongPathNameW
    api.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32)
    api.restype = ctypes.c_uint32
    buffer = ctypes.create_unicode_buffer(NATIVE_PATH_CAPACITY)
    length = api(str(path), buffer, len(buffer))
    value = buffer.value
    # Win32 reports UTF-16 code units; a supplementary character occupies two.
    units = len(value.encode("utf-16-le", errors="surrogatepass")) // 2
    if not length or length >= len(buffer) or not value or units != length:
        raise ValueError("invalid native spelling result")
    return value


def normalize_input_source(path: Path, root: Path | None = None) -> Path:
    """Admit one native entry spelling before dispatch, facts, or cache ownership.

Missing/non-file inputs retain their existing downstream handling. Existing
Windows files must expand to the same physical target; the lexical returned
name preserves separate discovered symlink/junction owners. No content is read.
"""
    if os.name != "nt":
        return path
    try:
        try:
            mode = path.stat().st_mode
        except (FileNotFoundError, NotADirectoryError):
            return path
        if not stat.S_ISREG(mode):
            return path
        physical = path.resolve(strict=True)
        expanded = Path(_native_long_name(path))
        if expanded.resolve(strict=True) != physical or not expanded.samefile(path):
            raise ValueError("native spelling changed physical input")
        return expanded
    except (OSError, RuntimeError, ValueError, AttributeError, ctypes.ArgumentError):
        source = json.dumps(_source_context(path, root), ensure_ascii=True)
        raise ValueError(f"SOURCE_INPUT_IDENTITY_FAILED: source={source}; native source "
                         "spelling unavailable; repair filesystem access and retry") from None


def resolved_source_owners(paths: list[Path], root: Path, *,
                          walked_relative: Callable[[Path, Path], Path],
                          realpath: Callable[[str, str], Path], cwd: str) -> dict[Path, Path]:
    """Choose shared physical ID ownership independently of input ordering.

Every walked source keeps its own primary identity. A supplied physical owner
owns its resolved spelling; one alias preserves the historical unique fallback.
Multiple aliases without that owner cannot authorize choosing one arbitrarily:
their shared target retains its portable physical ID without minting a node.
"""
    claims: dict[Path, set[Path]] = {}
    for path in paths:
        physical = realpath(str(path), cwd)
        try:
            relative = walked_relative(path, physical)
        except ValueError:
            continue
        claims.setdefault(physical, set()).add(relative)
    owners = {}
    for physical, relatives in claims.items():
        canonical = physical.relative_to(root)
        owners[physical] = (next(iter(relatives)) if len(relatives) == 1
                            else canonical)
        if canonical in relatives:
            owners[physical] = canonical
    return owners


def walked_relative_source(path: Path, root: Path, resolved: Path, *,
                           realpath: Callable[[str, str], Path], cwd: str) -> Path:
    """Reject foreign physical targets before retaining any written alias name.

Inputs are absolute source/root paths; root is the caller's canonical root.
No root/index/cache state is retained here and no accepted endpoint is minted.
The fallback handles platform aliases without a corresponding lexical ancestor.
"""
    relative = resolved.relative_to(root)
    try:
        return path.relative_to(root)
    except ValueError:
        for parent in path.parents:
            try:
                if realpath(str(parent), cwd) == root:
                    return path.relative_to(parent)
            except (OSError, RuntimeError):
                continue
    return relative
