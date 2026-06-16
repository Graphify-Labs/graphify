"""Blade template extractor for Laravel .blade.php files."""

from __future__ import annotations

import re
from pathlib import Path

from .registry import register
from ._utils import make_id

_EXTENSIONS = {".blade.php"}


@register(_EXTENSIONS)
def extract_blade(path: Path) -> dict:
    """Extract @include, <livewire:> components, and wire:click bindings from Blade templates."""
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"error": f"cannot read {path}"}

    file_nid = make_id(str(path))
    nodes = [
        {
            "id": file_nid,
            "label": path.name,
            "file_type": "code",
            "source_file": str(path),
            "source_location": None,
        }
    ]
    edges = []

    for m in re.finditer(r"@include\(['\"]([^'\"]+)['\"]", src):
        tgt = m.group(1).replace(".", "/")
        tgt_nid = make_id(tgt)
        if tgt_nid not in {n["id"] for n in nodes}:
            nodes.append(
                {
                    "id": tgt_nid,
                    "label": m.group(1),
                    "file_type": "code",
                    "source_file": str(path),
                    "source_location": None,
                }
            )
        edges.append(
            {
                "source": file_nid,
                "target": tgt_nid,
                "relation": "includes",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": str(path),
                "source_location": None,
                "weight": 1.0,
            }
        )

    for m in re.finditer(r"<livewire:([\w.\-]+)", src):
        tgt_nid = make_id(m.group(1))
        if tgt_nid not in {n["id"] for n in nodes}:
            nodes.append(
                {
                    "id": tgt_nid,
                    "label": m.group(1),
                    "file_type": "code",
                    "source_file": str(path),
                    "source_location": None,
                }
            )
        edges.append(
            {
                "source": file_nid,
                "target": tgt_nid,
                "relation": "uses_component",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": str(path),
                "source_location": None,
                "weight": 1.0,
            }
        )

    for m in re.finditer(r'wire:click=["\']([^"\']+)["\']', src):
        tgt_nid = make_id(m.group(1))
        if tgt_nid not in {n["id"] for n in nodes}:
            nodes.append(
                {
                    "id": tgt_nid,
                    "label": m.group(1),
                    "file_type": "code",
                    "source_file": str(path),
                    "source_location": None,
                }
            )
        edges.append(
            {
                "source": file_nid,
                "target": tgt_nid,
                "relation": "binds_method",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": str(path),
                "source_location": None,
                "weight": 1.0,
            }
        )

    return {"nodes": nodes, "edges": edges}
