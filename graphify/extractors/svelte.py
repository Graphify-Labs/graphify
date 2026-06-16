"""Svelte component extractor with template import detection."""

from __future__ import annotations

import os
import re
from pathlib import Path

from .registry import register
from ._utils import make_id

_EXTENSIONS = {".svelte"}


@register(_EXTENSIONS)
def extract_svelte(path: Path) -> dict:
    """Extract imports from .svelte files: script-block via JS AST + template regex fallback.

    Tree-sitter only sees the <script> block. Svelte template syntax like
    {#await import('./X.svelte')} lives in the markup layer and is invisible
    to the JS parser, so a regex pass covers those dynamic imports.
    """
    from ..extract import (
        _extract_generic,
        _JS_CONFIG,
        _load_tsconfig_aliases,
        _resolve_js_module_path,
    )

    result = _extract_generic(path, _JS_CONFIG)
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        existing_ids = {n["id"] for n in result.get("nodes", [])}
        file_node_id = make_id(str(path))
        aliases = _load_tsconfig_aliases(path.parent)
        for m in re.finditer(r"""import\(\s*['"]([^'"]+)['"]\s*\)""", src):
            raw = m.group(1)
            if not raw:
                continue
            if raw.startswith("."):
                resolved = Path(os.path.normpath(path.parent / raw))
                resolved = _resolve_js_module_path(resolved)
                node_id = make_id(str(resolved))
                stub_source_file = str(resolved)
            else:
                resolved_alias = None
                for alias_prefix, alias_base in aliases.items():
                    if raw == alias_prefix or raw.startswith(alias_prefix + "/"):
                        rest = raw[len(alias_prefix) :].lstrip("/")
                        resolved_alias = Path(os.path.normpath(Path(alias_base) / rest))
                        break
                if resolved_alias is not None:
                    resolved_alias = _resolve_js_module_path(resolved_alias)
                    node_id = make_id(str(resolved_alias))
                    stub_source_file = str(resolved_alias)
                else:
                    module_name = raw.split("/")[-1]
                    if not module_name:
                        continue
                    node_id = make_id(module_name)
                    stub_source_file = raw
            if node_id in existing_ids:
                result.setdefault("edges", []).append(
                    {
                        "source": file_node_id,
                        "target": node_id,
                        "relation": "dynamic_import",
                        "confidence": "EXTRACTED",
                        "source_file": str(path),
                    }
                )
                continue
            result.setdefault("nodes", []).append(
                {
                    "id": node_id,
                    "label": raw,
                    "file_type": "code",
                    "source_file": stub_source_file,
                    "confidence": "EXTRACTED",
                }
            )
            result.setdefault("edges", []).append(
                {
                    "source": file_node_id,
                    "target": node_id,
                    "relation": "dynamic_import",
                    "confidence": "EXTRACTED",
                    "source_file": str(path),
                }
            )
            existing_ids.add(node_id)
        script_re = re.compile(r"<script\b[^>]*>([\s\S]*?)</script\s*>", re.IGNORECASE)
        static_import_re = re.compile(r"""import\s+(?:[^'"`;]+?\s+from\s+)?['"]([^'"]+)['"]""")
        for script_match in script_re.finditer(src):
            script_body = script_match.group(1)
            for m in static_import_re.finditer(script_body):
                raw = m.group(1)
                if not raw:
                    continue
                if raw.startswith("."):
                    resolved = Path(os.path.normpath(path.parent / raw))
                    if resolved.suffix == ".js":
                        resolved = resolved.with_suffix(".ts")
                    elif resolved.suffix == ".jsx":
                        resolved = resolved.with_suffix(".tsx")
                    node_id = make_id(str(resolved))
                    stub_source_file = str(resolved)
                else:
                    resolved_alias = None
                    for alias_prefix, alias_base in aliases.items():
                        if raw == alias_prefix or raw.startswith(alias_prefix + "/"):
                            rest = raw[len(alias_prefix) :].lstrip("/")
                            resolved_alias = Path(os.path.normpath(Path(alias_base) / rest))
                            break
                    if resolved_alias is not None:
                        node_id = make_id(str(resolved_alias))
                        stub_source_file = str(resolved_alias)
                    else:
                        module_name = raw.split("/")[-1]
                        if not module_name:
                            continue
                        node_id = make_id(module_name)
                        stub_source_file = raw
                if node_id in existing_ids:
                    result.setdefault("edges", []).append(
                        {
                            "source": file_node_id,
                            "target": node_id,
                            "relation": "imports_from",
                            "confidence": "EXTRACTED",
                            "source_file": str(path),
                        }
                    )
                    continue
                result.setdefault("nodes", []).append(
                    {
                        "id": node_id,
                        "label": raw,
                        "file_type": "code",
                        "source_file": stub_source_file,
                        "confidence": "EXTRACTED",
                    }
                )
                result.setdefault("edges", []).append(
                    {
                        "source": file_node_id,
                        "target": node_id,
                        "relation": "imports_from",
                        "confidence": "EXTRACTED",
                        "source_file": str(path),
                    }
                )
                existing_ids.add(node_id)
    except Exception:
        pass
    return result
