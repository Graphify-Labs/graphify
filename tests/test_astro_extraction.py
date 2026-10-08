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


def _labels(result: dict) -> dict[str, str]:
    """Label -> source_location for every node except the file node."""
    return {
        str(n.get("label")): str(n.get("source_location"))
        for n in result.get("nodes", [])
        if n.get("id") != result.get("nodes", [{}])[0].get("id")
    }


def test_extract_astro_template_is_not_a_parse_error(tmp_path):
    """The template is not TS; only frontmatter and <script> bodies are parsed (#2788).

    Parsing the whole file as JS reported every page as a syntax error, and
    symbols the parser could not recover past the template were dropped.
    """
    page = _write(
        tmp_path / "src/pages/results.astro",
        """---
import Layout from '../layouts/Layout.astro';
interface Props { year: number }
const { year } = Astro.props;
function rank(scores: number[]): number[] {
  return [...scores].sort((a, b) => b - a);
}
---

<Layout title={`Results ${year}`}>
  <ol>{rank([3, 1, 2]).map((s) => <li class="score">{s}</li>)}</ol>
</Layout>
<script type="application/ld+json">{ "@type": "Event", "name": "x" }</script>
<script>
  function toggle(el: HTMLElement) { el.classList.toggle('open'); }
  document.querySelectorAll('ol').forEach((el) => toggle(el));
</script>
""",
    )
    result = extract_astro(page)
    assert result.get("parse_errors") is None
    labels = _labels(result)
    assert "rank()" in labels and "toggle()" in labels
    # Masking keeps offsets, so locations still point at the original lines.
    assert labels["rank()"] == "L5"
    assert labels["toggle()"] == "L15"


def test_extract_astro_scripts_on_one_line_do_not_merge(tmp_path):
    """Two script bodies on one line must not parse as a single statement."""
    page = _write(
        tmp_path / "src/pages/inline.astro",
        "<script>const a = 1</script><script>function b() {}</script>\n",
    )
    result = extract_astro(page)
    assert result.get("parse_errors") is None
    assert "b()" in _labels(result)


def test_extract_astro_trailing_comment_does_not_hide_next_script(tmp_path):
    """A comment at the closing tag must end before the next script (#4072)."""
    page = _write(
        tmp_path / "inline-comment.astro",
        "<script>const a = 1 // trailing comment</script>"
        "<script>function visible() {}</script>\n",
    )
    result = extract_astro(page)
    assert result.get("parse_errors") is None
    assert _labels(result)["visible()"] == "L1"


def test_astro_mask_preserves_bytes_and_newlines_after_comment():
    from graphify.extract import _astro_mask_non_script

    source = (
        "---\nconst title = 'hello';\n---\n"
        "<script>const a = 1 // comment</script>"
        "<script>function visible() {}</script>\r\n"
    )
    masked = _astro_mask_non_script(source).encode("utf-8")
    original = source.encode("utf-8")
    assert len(masked) == len(original)
    assert masked.index(b"function visible") == original.index(b"function visible")
    assert [(i, c) for i, c in enumerate(masked) if c in (10, 13)] == [
        (i, c) for i, c in enumerate(original) if c in (10, 13)
    ]
