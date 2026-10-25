"""A cache entry whose path exceeds Windows MAX_PATH must still save and load.

Under a deep root (a nested temp dir, OneDrive, a long user name) the AST cache
path — <root>/graphify-out/cache/ast/v<ver>-s<schema>-g<grammars>/<64 hex>.json,
plus mkstemp's longer ``<hash>.<random>.tmp`` temp name — overruns 260 chars.
The write raised FileNotFoundError and ``graphify extract`` failed outright.
"""
from __future__ import annotations

import os

import pytest

from graphify.cache import cache_dir, load_cached, save_cached
from graphify.paths import _WINDOWS_MAX_PATH


@pytest.mark.skipif(os.name != "nt", reason="Windows MAX_PATH semantics")
def test_cache_entry_round_trips_past_windows_max_path(tmp_path):
    src = tmp_path / "a.py"
    src.write_text("def f():\n    return 1\n", encoding="utf-8")

    # Pad the cache root so the cache DIRECTORY stays creatable (< 248) while
    # the entry file inside it (+ "\<64 hex>.json") lands past MAX_PATH.
    overhead = len(str(cache_dir(tmp_path / "p", "ast"))) - len(str(tmp_path / "p"))
    deep = tmp_path / ("d" * (230 - overhead - len(str(tmp_path)) - 1))
    entry_len = len(str(cache_dir(deep, "ast"))) + 1 + 64 + len(".json")
    assert entry_len > _WINDOWS_MAX_PATH - 1, entry_len

    result = {"nodes": [{"id": "f", "label": "f", "source_file": str(src)}], "edges": []}
    save_cached(src, result, root=tmp_path, cache_root=deep)

    cached = load_cached(src, root=tmp_path, cache_root=deep)
    assert cached is not None
    assert [n["label"] for n in cached["nodes"]] == ["f"]
    assert not list(cache_dir(deep, "ast").glob("*.tmp"))
