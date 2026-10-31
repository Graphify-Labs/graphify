"""Every production call site must state both cache roots explicitly (#4831).

`save_semantic_cache` and `check_semantic_cache` take `root` (the anchor used to
resolve and relativize source paths) and `cache_root` (where entries are stored).
Omitting `cache_root` collapses them, which is only correct when there is no
`--out`. That collapse is exactly what #4831 was: the save call passed
`root=out_root` and nothing else.

The API cannot require `cache_root` without breaking the documented skill flows
that call these functions directly, so this test pins the call sites instead:
a new caller that forgets `cache_root` fails here rather than in a user's token
bill.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TARGETS = {"save_semantic_cache", "check_semantic_cache"}
FORBIDDEN_OMISSION = {"root", "cache_root"}


def _calls_missing_cache_root(tree: ast.AST) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        name = name.lstrip("_")
        if name not in TARGETS:
            continue
        keywords = {k.arg for k in node.keywords if k.arg}
        if not FORBIDDEN_OMISSION <= keywords:
            found.append((node.lineno, name))
    return found


def test_production_semantic_cache_calls_pass_cache_root():
    offenders: list[str] = []
    for path in sorted((REPO / "graphify").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno, name in _calls_missing_cache_root(tree):
            offenders.append(f"{path.relative_to(REPO)}:{lineno} {name}(...)")

    assert not offenders, (
        "semantic cache call site(s) omit root=/cache_root=, so a corpus-relative "
        "source_file would be resolved against the output root (#4831):\n  "
        + "\n  ".join(offenders)
    )


def test_guard_detects_the_historical_bug_shape():
    """Self-check: the guard must fail on the v0.9.7 call shape."""
    bad = ast.parse("save_semantic_cache(nodes, [], root=out_root)")
    assert _calls_missing_cache_root(bad) == [(1, "save_semantic_cache")]

    good = ast.parse("save_semantic_cache(nodes, [], root=target, cache_root=out_root)")
    assert _calls_missing_cache_root(good) == []


def test_all_keyword_args_are_accepted_by_the_real_functions():
    """The guard's required keywords must exist on the functions it polices."""
    import inspect

    from graphify.cache import check_semantic_cache, save_semantic_cache

    for fn in (check_semantic_cache, save_semantic_cache):
        params = inspect.signature(fn).parameters
        assert FORBIDDEN_OMISSION <= set(params), f"{fn.__name__} lost {FORBIDDEN_OMISSION - set(params)}"
