"""Shopify theme JSON extractor (deterministic).

Links the JSON files that describe page structure in an Online Store 2.0 theme to
the Liquid files they place, so ``graphify affected sections/featured.liquid``
lists the templates and section groups that use it:

* ``templates/*.json`` and ``sections/*.json`` (section groups, including their
  ``.context.<x>.json`` variants): each ``sections`` entry -> ``sections/<type>.liquid``
  (``imports``), each nested ``blocks`` entry -> ``blocks/<type>.liquid`` when
  that file exists (``imports``).
* ``config/settings_data.json``: the same placement for ``current.sections`` and
  each ``presets.<name>.sections`` (legacy section groups saved by the editor).
* ``config/settings_schema.json``, and ``{% schema %}`` bodies read by the Liquid
  extractor: ``"t:key"`` strings -> the key in the single
  ``locales/*.default.schema.json`` (``references``).

Routing gate: ``is_shopify_theme_json_path`` is true only for the paths above
inside a theme root (an ancestor with ``layout/theme.liquid``). Any other JSON keeps
the generic routing, and a template carrying ``$schema`` is read here, not as
config. A leading ``/* ... */`` banner is ignored; a file that does not parse
yields only its file node.

Placement edges follow sorted key order and point at line 1, so reordering the
keys of a template does not change the extraction.

Not covered: app blocks (``shopify://`` and ``@app`` types), the built-in ``_blocks``
section type (its nested blocks are still linked), block types with no
``blocks/<type>.liquid`` (they may be section-local, so nothing is guessed),
and the ``{% block %}`` / ``{% partial %}`` tags.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from graphify.extractors.base import _read_source_text
from graphify.extractors.liquid import (
    _strip_json_comments,
    _Collector,
    _find_theme_root,
    _safe_component,
    _settings_schema,
    setting_node,
)

_MAX_JSON_BYTES = 1024 * 1024
_MAX_DEPTH = 32
_SETTINGS_SCHEMA = ("config", "settings_schema.json")
_SETTINGS_DATA = ("config", "settings_data.json")


def _relative_parts(path: Path) -> tuple[Path, tuple[str, ...]] | None:
    """Theme root and the path parts below it, or None outside a theme."""
    path = Path(os.path.abspath(path))
    root = _find_theme_root(path)
    if root is None:
        return None
    try:
        return root, path.relative_to(root).parts
    except ValueError:
        return None


def is_shopify_theme_json_path(path: Path) -> bool:
    """True for a theme template, section group or settings schema inside a theme root."""
    if path.suffix.lower() != ".json":
        return False
    found = _relative_parts(path)
    if found is None:
        return False
    parts = found[1]
    if parts[:1] == ("templates",):
        return 2 <= len(parts) <= 3
    if parts[:1] == ("sections",):
        return len(parts) == 2
    return parts in (_SETTINGS_SCHEMA, _SETTINGS_DATA)


def _is_app(block_type: str) -> bool:
    return block_type.startswith(("shopify://", "@"))


def _is_builtin_section(section_type: str) -> bool:
    """``_blocks`` is a section type Shopify provides; it has no ``sections/`` file."""
    return section_type == "_blocks"


def _walk_blocks(blocks: object, out: _Collector, depth: int) -> None:
    """Edge to ``blocks/<type>.liquid`` for each nested block that has such a file."""
    if depth > _MAX_DEPTH or not isinstance(blocks, dict):
        return
    for key in sorted(blocks):
        entry = blocks[key]
        if not isinstance(entry, dict):
            continue
        block_type = entry.get("type")
        if isinstance(block_type, str) and not _is_app(block_type) and _safe_component(block_type):
            target = out.root / "blocks" / f"{block_type}.liquid"
            if target.is_file():
                out.file_edge("imports", "block", block_type, target, 1)
        _walk_blocks(entry.get("blocks"), out, depth + 1)


def _place_sections(data: dict, out: _Collector) -> None:
    sections = data.get("sections")
    if not isinstance(sections, dict):
        return
    for key in sorted(sections):
        entry = sections[key]
        if not isinstance(entry, dict):
            continue
        section_type = entry.get("type")
        if not isinstance(section_type, str) or _is_app(section_type) or not _safe_component(section_type):
            continue
        if not _is_builtin_section(section_type):
            out.file_edge("imports", "section", section_type, out.root / "sections" / f"{section_type}.liquid", 1)
        _walk_blocks(entry.get("blocks"), out, 0)


def extract_shopify_theme_json(path: Path) -> dict:
    """Extract section and block placement from a theme template or section group.

    Returns only the file node when the JSON cannot be read or parsed.
    """
    path = Path(os.path.abspath(path))
    found = _relative_parts(path)
    out = _Collector(path, found[0] if found is not None else path.parent)
    empty = {"nodes": out.nodes, "edges": out.edges}
    if found is None:
        return empty
    try:
        if path.stat().st_size > _MAX_JSON_BYTES and found[1] != _SETTINGS_SCHEMA:
            return empty
        src = _read_source_text(path)
        data = json.loads(_strip_json_comments(src))
    except (OSError, ValueError, RecursionError):
        return empty
    if found[1] == _SETTINGS_SCHEMA:
        out.schema_keys(data, src, 1)
        for sid, line in (_settings_schema(out.root) or {}).items():
            node = setting_node(out.root, sid, line)
            out.nodes.append(node)
            out.edges.append({
                "source": out.file_id, "target": node["id"], "relation": "contains",
                "confidence": "EXTRACTED", "confidence_score": 1.0,
                "source_file": str(path), "source_location": f"L{line}", "weight": 1.0,
            })
    elif found[1] == _SETTINGS_DATA:
        if isinstance(data, dict):
            scopes = [data.get("current")]
            presets = data.get("presets")
            if isinstance(presets, dict):
                scopes.extend(presets[k] for k in sorted(presets))
            for scope in scopes:
                if isinstance(scope, dict):
                    _place_sections(scope, out)
    elif isinstance(data, dict):
        _place_sections(data, out)
    return {"nodes": out.nodes, "edges": out.edges}
