"""The in-flight scan root is shared through extractors.base, not by reaching
back into graphify.extract — MIGRATION.md invariant #4 (#3666)."""
from __future__ import annotations

import ast
from pathlib import Path

from graphify.extractors import base as base_mod
from graphify.extractors import markdown as markdown_mod


def _imports_graphify_extract(module) -> bool:
    """True if the module's source imports graphify.extract anywhere — a
    top-level or a function-local `import graphify.extract` / `from
    graphify.extract import ...`."""
    source = Path(module.__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            if any(a.name == "graphify.extract" or a.name.startswith("graphify.extract.")
                   for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "graphify.extract" or (node.module or "").startswith("graphify.extract."):
                return True
    return False


def test_markdown_extractor_does_not_import_graphify_extract():
    """The Markdown extractor read the in-flight scan root via a function-local
    `import graphify.extract` + getattr, a package->parent dependency that
    violated invariant #4 and degraded silently on a rename (#3666). It must now
    reach the shared context through extractors.base instead."""
    assert not _imports_graphify_extract(markdown_mod), (
        "extractors/markdown.py must not import graphify.extract — read the scan "
        "root via extractors.base.active_scan_root() (MIGRATION.md invariant #4)"
    )


def test_active_scan_root_defaults_to_none():
    # A fresh process (no extraction in flight) has no active root.
    assert base_mod.active_scan_root() is None


def test_active_scan_root_set_get_restore_nested():
    """set_active_scan_root returns the previous value so nested extraction can
    restore it; active_scan_root reflects the current top of that stack."""
    assert base_mod.active_scan_root() is None
    outer = Path("/repo").resolve()
    inner = Path("/repo/vendored").resolve()

    prev_outer = base_mod.set_active_scan_root(outer)
    try:
        assert prev_outer is None
        assert base_mod.active_scan_root() == outer

        prev_inner = base_mod.set_active_scan_root(inner)
        try:
            assert prev_inner == outer
            assert base_mod.active_scan_root() == inner
        finally:
            base_mod.set_active_scan_root(prev_inner)

        assert base_mod.active_scan_root() == outer
    finally:
        base_mod.set_active_scan_root(prev_outer)

    assert base_mod.active_scan_root() is None


def test_markdown_active_scan_root_alias_is_base_accessor():
    """The Markdown extractor's _active_scan_root is the base accessor, so the
    scan root extract() publishes is exactly what link resolution reads."""
    assert markdown_mod._active_scan_root is base_mod.active_scan_root
