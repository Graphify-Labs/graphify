"""Tests for `.astro` extraction (#850).

Astro files have a TypeScript frontmatter block (`---...---`) at the top where
nearly all imports live, followed by an HTML-with-expressions template and
optionally `<script>` blocks. Tree-sitter-javascript fed the whole file produces
a top-level ERROR node because the template is not valid JS, so the JS AST pass
recovers nothing. The :func:`extract_astro` regex pass salvages imports from the
frontmatter and any `<script>` blocks — same strategy as :func:`extract_svelte`.
"""
from __future__ import annotations

from pathlib import Path

from graphify.detect import CODE_EXTENSIONS
from graphify.extract import (
    _make_id,
    extract_astro,
)


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


def test_astro_is_in_code_extensions():
    """Without this, detect.py silently drops `.astro` from the AST pass (#850)."""
    assert ".astro" in CODE_EXTENSIONS


def test_extract_astro_picks_up_frontmatter_static_imports(tmp_path):
    page = _write(
        tmp_path / "src/pages/index.astro",
        """---
import Layout from '../layouts/Layout.astro';
import Hero from '../components/Hero.astro';
const { title } = Astro.props;
---

<Layout title={title}>
  <Hero />
</Layout>
""",
    )
    # Sibling files so the resolver lands on real node ids, not phantoms.
    layout = _write(tmp_path / "src/layouts/Layout.astro", "---\n---\n<slot />\n")
    hero = _write(tmp_path / "src/components/Hero.astro", "---\n---\n<h1>hi</h1>\n")

    result = extract_astro(page)
    targets = _import_targets(result, relation="imports_from")
    assert _make_id(str(layout)) in targets
    assert _make_id(str(hero)) in targets


def test_extract_astro_handles_dynamic_import_in_frontmatter(tmp_path):
    page = _write(
        tmp_path / "src/pages/lazy.astro",
        """---
const Mod = await import('./Other.astro');
---

<div>{Mod.default}</div>
""",
    )
    other = _write(tmp_path / "src/pages/Other.astro", "---\n---\n<p>o</p>\n")

    result = extract_astro(page)
    targets = _import_targets(result, relation="dynamic_import")
    assert _make_id(str(other)) in targets


def test_extract_astro_picks_up_client_side_script_imports(tmp_path):
    page = _write(
        tmp_path / "src/pages/with-script.astro",
        """---
import Layout from '../layouts/Layout.astro';
---

<Layout>
  <button id="b">click</button>
</Layout>

<script>
  import { hydrate } from '../client/hydrate.ts';
  hydrate(document.getElementById('b'));
</script>
""",
    )
    layout = _write(tmp_path / "src/layouts/Layout.astro", "---\n---\n<slot />\n")
    hydrate = _write(tmp_path / "src/client/hydrate.ts", "export function hydrate(){}\n")

    result = extract_astro(page)
    targets = _import_targets(result, relation="imports_from")
    assert _make_id(str(layout)) in targets
    assert _make_id(str(hydrate)) in targets


def test_extract_astro_no_frontmatter_does_not_crash(tmp_path):
    """Astro permits frontmatter-less files (pure-HTML pages). Must not raise."""
    page = _write(
        tmp_path / "src/pages/plain.astro",
        "<h1>no frontmatter here</h1>\n",
    )
    result = extract_astro(page)
    # Empty/no-imports result is acceptable; the extractor must just not crash.
    assert isinstance(result, dict)
    assert _import_targets(result, relation="imports_from") == set()


def test_extract_astro_handles_tsconfig_path_alias(tmp_path):
    _write(
        tmp_path / "tsconfig.json",
        """{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": { "@components/*": ["src/components/*"] }
  }
}
""",
    )
    page = _write(
        tmp_path / "src/pages/alias.astro",
        """---
import Hero from '@components/Hero.astro';
---

<Hero />
""",
    )
    hero = _write(tmp_path / "src/components/Hero.astro", "---\n---\n<h1>h</h1>\n")

    result = extract_astro(page)
    targets = _import_targets(result, relation="imports_from")
    assert _make_id(str(hero)) in targets


def test_extract_astro_captures_script_block_symbols(tmp_path):
    """The `<script>` block is client-side code, and its symbols belong in the
    graph (#3337).

    Feeding the whole `.astro` file to the JS grammar makes tree-sitter fail at
    the template and recover only partially. `.vue` avoids this by blanking
    everything outside the script regions before parsing; `.astro` has the same
    two regions (frontmatter and `<script>`), so it can use the same treatment.
    The callback published on `window` is the reason this matters: a third-party
    widget invokes it by name, so nothing in the module graph points at it.
    """
    page = _write(
        tmp_path / "src/components/Form.astro",
        """---
const endpoint = '/api/contact';
---

<form id="f"><button>go</button></form>

<script>
  function invia(token) {
    return fetch('/api/contact', { method: 'POST', body: token });
  }
  window.onWidgetOk = (token) => { invia(token); };
</script>
""",
    )
    labels = [n["label"] for n in extract_astro(page)["nodes"]]
    assert "invia()" in labels
    assert "window.onWidgetOk()" in labels


def test_extract_astro_script_word_in_frontmatter_comment_is_not_a_block(tmp_path):
    """A `<script>` written inside the frontmatter is prose, not a block (#3337).

    Found in the wild: a comment reading "do not duplicate the dictionary inside
    the <script>". Matched as a real opening tag, it opens a block that runs to
    the actual `</script>` hundreds of lines below, so masking keeps the wrong
    span and the entire client-side region is blanked instead of parsed.
    """
    page = _write(
        tmp_path / "src/components/Commented.astro",
        """---
// keep this in sync, do not duplicate the labels inside the <script>.
const label = 'go';
---

<button>{label}</button>

<script>
  function realeDavvero() { return 1; }
  window.onPublished = () => realeDavvero();
</script>
""",
    )
    labels = [n["label"] for n in extract_astro(page)["nodes"]]
    assert "realeDavvero()" in labels
    assert "window.onPublished()" in labels
