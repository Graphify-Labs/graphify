"""The in-flight scan root is shared through extractors.base, not by reaching
back into graphify.extract — MIGRATION.md invariant #4 (#3666)."""
from __future__ import annotations

import ast
from pathlib import Path

import graphify.extractors as extractors_pkg
from graphify.extractors import base as base_mod
from graphify.extractors import markdown as markdown_mod


def _imports_graphify_extract(source_or_path, *, package_depth: int = 1) -> list[int]:
    """Line numbers of every import of the graphify.extract facade, in any form.

    Accepts a Path (read as UTF-8) or source text. `package_depth` is how many
    directories below the `graphify` package the file sits (1 for a module
    directly in graphify/extractors/), so relative imports can be resolved.
    Flagged forms: `import graphify.extract[.x]`, `from graphify.extract[.x]
    import ...`, `from graphify import extract`, `from ..extract import ...`
    and `from .. import extract`. `graphify.extractors...` is not flagged.
    The source is parsed, never imported."""
    if isinstance(source_or_path, Path):
        source = source_or_path.read_text(encoding="utf-8")
    else:
        source = source_or_path

    def is_facade(name: str) -> bool:
        return name == "graphify.extract" or name.startswith("graphify.extract.")

    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            if any(is_facade(a.name) for a in node.names):
                lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level == 0:
                hit = is_facade(mod) or (
                    mod == "graphify" and any(a.name == "extract" for a in node.names)
                )
            elif node.level == package_depth + 1:
                # Relative import that lands on the graphify package itself.
                hit = (
                    mod == "extract" or mod.startswith("extract.")
                    or (mod == "" and any(a.name == "extract" for a in node.names))
                )
            else:
                hit = False
            if hit:
                lines.append(node.lineno)
    return sorted(lines)


def test_markdown_extractor_does_not_import_graphify_extract():
    """The Markdown extractor read the in-flight scan root via a function-local
    `import graphify.extract` + getattr, a package->parent dependency that
    violated invariant #4 and degraded silently on a rename (#3666). It must now
    reach the shared context through extractors.base instead."""
    assert not _imports_graphify_extract(Path(markdown_mod.__file__)), (
        "extractors/markdown.py must not import graphify.extract — read the scan "
        "root via extractors.base.active_scan_root() (MIGRATION.md invariant #4)"
    )


def test_no_extractor_module_imports_graphify_extract():
    """Package-wide guard for MIGRATION.md invariant #4 (#3666): nothing under
    graphify/extractors/ may import the graphify.extract facade."""
    pkg_dir = Path(extractors_pkg.__file__).parent
    offenders = []
    for path in sorted(pkg_dir.rglob("*.py")):
        depth = len(path.parent.relative_to(pkg_dir).parts) + 1
        for lineno in _imports_graphify_extract(path, package_depth=depth):
            offenders.append(f"{path.relative_to(pkg_dir.parent.parent).as_posix()}:{lineno}")
    assert not offenders, (
        "graphify/extractors/ must never import graphify.extract (MIGRATION.md "
        "invariant #4, #3666); import direction is extract.py -> extractors/. "
        "Offending imports: " + ", ".join(offenders)
    )


def test_import_guard_flags_every_facade_form():
    flagged = [
        "import graphify.extract",
        "import graphify.extract.sub",
        "from graphify.extract import _x",
        "from graphify import extract",
        "from ..extract import _x",
        "from .. import extract",
    ]
    for src in flagged:
        assert _imports_graphify_extract(src) == [1], src
    assert _imports_graphify_extract("def f():\n    import graphify.extract\n") == [2]
    for src in ("import graphify.extractors.base", "from graphify.extractors import base",
                "from .base import x", "from ..ids import make_id", "from graphify import ids"):
        assert _imports_graphify_extract(src) == [], src


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
