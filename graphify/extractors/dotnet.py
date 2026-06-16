""".NET project file extractors - delegates to extract.py implementation."""

from __future__ import annotations

from pathlib import Path

from .registry import register

_SLN_EXTENSIONS = {".sln"}
_SLNX_EXTENSIONS = {".slnx"}
_PROJ_EXTENSIONS = {".csproj", ".fsproj", ".vbproj"}


@register(_SLN_EXTENSIONS)
def extract_sln(path: Path) -> dict:
    """Extract projects and inter-project dependencies from a .sln file."""
    from ._core import extract_sln as _extract_sln

    return _extract_sln(path)


@register(_SLNX_EXTENSIONS)
def extract_slnx(path: Path) -> dict:
    """Extract projects and inter-project dependencies from a .slnx file."""
    from ._core import extract_slnx as _extract_slnx

    return _extract_slnx(path)


@register(_PROJ_EXTENSIONS)
def extract_csproj(path: Path) -> dict:
    """Extract packages, project refs, and target framework from a .csproj/.fsproj/.vbproj."""
    from ._core import extract_csproj as _extract_csproj

    return _extract_csproj(path)
