"""Tests for ``.svelte`` and ``.astro`` script masking.

Feeding a whole ``.svelte`` or ``.astro`` file to the JS grammar produces a
top-level ERROR node, so the AST pass is abandoned and only the regex rescue
contributes — imports survive, every declaration is lost.
:func:`extract_svelte` and :func:`extract_astro` now mask the non-code regions
and parse the real script with the TypeScript grammar, mirroring
:func:`extract_vue`.
"""
from __future__ import annotations

from pathlib import Path

from graphify.detect import CODE_EXTENSIONS
from graphify.extract import extract_astro, extract_svelte
from graphify.extractors.resolution import _astro_mask, _vue_mask_non_script


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _labels(result: dict) -> set[str]:
    return {str(n.get("label") or "") for n in result.get("nodes", [])}


def _targets(result: dict, *, relation: str | None = None) -> set[str]:
    return {
        str(e.get("target") or "")
        for e in result.get("edges", [])
        if relation is None or e.get("relation") == relation
    }


SVELTE_SRC = """\
<script lang="ts">
  import { onMount } from 'svelte';
  import Child from './Child.svelte';

  interface Props { title: string }

  const greeting = 'hello';

  export function formatTitle(t: string): string {
    return t.toUpperCase();
  }

  function handleClick() {
    formatTitle(greeting);
  }
</script>

<div on:click={handleClick}>
  <Child />
  {#if greeting}<span>{greeting}</span>{/if}
</div>

<style>
  div { color: red; }
</style>
"""

ASTRO_SRC = """\
---
import Layout from '../layouts/Layout.astro';
import { getItems } from '../lib/items';

interface PageProps { slug: string }

const items = await getItems();

function renderCount(n: number): string {
  return `${n} items`;
}
---

<Layout>
  <p>{renderCount(items.length)}</p>
</Layout>

<script>
  const clientOnly = 'browser';
  console.log(clientOnly);
</script>
"""


def test_extensions_registered():
    assert ".svelte" in CODE_EXTENSIONS
    assert ".astro" in CODE_EXTENSIONS


def test_svelte_mask_preserves_line_numbers_and_blanks_markup():
    masked, lang = _vue_mask_non_script(SVELTE_SRC)
    assert lang == "ts"
    assert len(masked.splitlines()) == len(SVELTE_SRC.splitlines())
    # Script body survives; markup and style do not.
    assert "formatTitle" in masked
    assert "color: red" not in masked
    assert "on:click" not in masked


def test_astro_mask_preserves_line_numbers_and_blanks_template():
    masked = _astro_mask(ASTRO_SRC)
    assert len(masked.splitlines()) == len(ASTRO_SRC.splitlines())
    assert "renderCount" in masked
    assert "clientOnly" in masked  # client <script> kept
    assert "<Layout>" not in masked


def test_astro_mask_frontmatter_only_drops_client_script():
    masked = _astro_mask(ASTRO_SRC, include_scripts=False)
    assert "renderCount" in masked
    assert "clientOnly" not in masked


def test_astro_mask_without_frontmatter_is_safe():
    src = "<h1>no frontmatter here</h1>\n"
    masked = _astro_mask(src)
    assert masked.strip() == ""
    assert len(masked.splitlines()) == len(src.splitlines())


def test_svelte_extraction_recovers_declarations(tmp_path: Path):
    path = _write(tmp_path / "Widget.svelte", SVELTE_SRC)
    result = extract_svelte(path)
    assert not result.get("error")
    labels = _labels(result)
    # Declarations that the pre-masking extractor could never see. Function
    # labels carry a "()" suffix; interfaces do not.
    assert "formatTitle()" in labels
    assert "handleClick()" in labels
    assert "Props" in labels
    # Imports still resolve, as before.
    assert any("svelte" in t or "Child" in t for t in _targets(result))


def test_astro_extraction_recovers_declarations(tmp_path: Path):
    path = _write(tmp_path / "page.astro", ASTRO_SRC)
    result = extract_astro(path)
    assert not result.get("error")
    labels = _labels(result)
    assert "renderCount()" in labels
    assert "PageProps" in labels
    assert any("items" in t or "Layout" in t for t in _targets(result))


def test_svelte_extraction_beats_unmasked_baseline(tmp_path: Path):
    """The masked pass must strictly add nodes, never lose them."""
    from graphify.extract import _JS_CONFIG
    from graphify.extractors.engine import _extract_generic

    path = _write(tmp_path / "Widget.svelte", SVELTE_SRC)
    unmasked = _extract_generic(path, _JS_CONFIG)
    masked = extract_svelte(path)
    assert len(masked.get("nodes", [])) > len(unmasked.get("nodes", []))
