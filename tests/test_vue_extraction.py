"""Tests for `.vue` extraction.

A `.vue` Single-File Component has the same ``<template>``/``<script>``/``<style>``
structure as a ``.svelte`` file: tree-sitter-javascript fed the whole file produces a
top-level ERROR node (the markup is not valid JS), so the JS AST pass never reaches the
``import_statement`` nodes inside ``<script>``/``<script setup>`` and they are silently
dropped. The Svelte regex rescue (#713) recovers them, and ``.vue`` reuses it.
"""

from __future__ import annotations

from pathlib import Path

from graphify.detect import CODE_EXTENSIONS
from graphify.extract import _get_extractor, _make_id


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _import_targets(result: dict, *, relation: str | None = None) -> set[str]:
    return {
        str(e.get("target") or "")
        for e in result.get("edges", [])
        if relation is None or e.get("relation") == relation
    }


def test_vue_is_in_code_extensions():
    assert ".vue" in CODE_EXTENSIONS


def test_extract_vue_picks_up_script_static_imports(tmp_path):
    page = _write(
        tmp_path / "src/App.vue",
        """<script setup>
import Hero from './components/Hero.vue';
</script>

<template>
  <Hero />
</template>
""",
    )
    # Sibling file so the resolver lands on a real node id, not a phantom.
    hero = _write(tmp_path / "src/components/Hero.vue", "<template><h1>hi</h1></template>\n")

    extractor = _get_extractor(page)
    result = extractor(page)
    targets = _import_targets(result, relation="imports_from")
    assert _make_id(str(hero)) in targets
