"""JS/TS resolution filter is a separate constant from the AST cache gate.

`_JS_CACHE_BYPASS_SUFFIXES` used to answer two unrelated questions: whether a
file skips the AST cache (`extract.py`) and whether it goes through JS/TS
cross-file symbol resolution (`resolution.py`). Narrowing the set for caching
reasons therefore dropped INFERRED edges with no error and almost no change in
node count. `_JS_FAMILY_SUFFIXES` now answers the language question, so the
cache gate can move independently.
"""
from __future__ import annotations

import inspect

from graphify.extractors import models, resolution


def test_family_and_cache_sets_agree_today():
    assert models._JS_FAMILY_SUFFIXES == models._JS_CACHE_BYPASS_SUFFIXES


def test_family_set_covers_the_js_ts_extensions():
    for suffix in (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".vue", ".svelte"):
        assert suffix in models._JS_FAMILY_SUFFIXES


def test_resolution_filters_on_the_language_set_not_the_cache_gate():
    src = inspect.getsource(resolution._collect_js_symbol_resolution_facts)
    assert "_JS_FAMILY_SUFFIXES" in src
    assert "_JS_CACHE_BYPASS_SUFFIXES" not in src


def test_narrowing_the_cache_gate_leaves_resolution_intact(monkeypatch):
    monkeypatch.setattr(models, "_JS_CACHE_BYPASS_SUFFIXES", frozenset())
    monkeypatch.setattr(resolution, "_JS_CACHE_BYPASS_SUFFIXES", frozenset())

    facts = resolution._SymbolResolutionFacts()
    resolution._collect_js_symbol_resolution_facts([], facts)

    assert ".ts" in resolution._JS_FAMILY_SUFFIXES
    assert ".vue" in resolution._JS_FAMILY_SUFFIXES
