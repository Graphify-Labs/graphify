"""Tests for `.svelte` extraction (#3928).

A `.svelte` file is markup with one or two `<script>` blocks. Tree-sitter fed
the whole file produces a top-level ERROR node at line 1 because the template is
not JS, so the AST pass never reached the `function_declaration` nodes inside
`<script>` — every component was reported as a syntax error and only its
imports survived, via the regex rescue pass. :func:`extract_svelte` masks the
markup and style regions and parses just the script bodies, the same strategy
:func:`extract_vue` and :func:`extract_astro` use.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import _make_id, extract_svelte


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _labels(result: dict) -> dict[str, str]:
    """Label -> source_location for every node except the file node."""
    file_id = result.get("nodes", [{}])[0].get("id")
    return {
        str(n.get("label")): str(n.get("source_location"))
        for n in result.get("nodes", [])
        if n.get("id") != file_id
    }


def _import_targets(result: dict, *, relation: str | None = None) -> set[str]:
    return {
        str(e.get("target") or "")
        for e in result.get("edges", [])
        if relation is None or e.get("relation") == relation
    }


def test_extract_svelte_template_is_not_a_parse_error(tmp_path):
    """The template is not JS; only `<script>` bodies are parsed (#3928).

    Parsing the whole file reported every component as a syntax error at line 1
    and dropped every symbol declared inside `<script>`.
    """
    component = _write(
        tmp_path / "src/A.svelte",
        """<script>
  import { foo } from "./x";
  let n = 1;
  function bump() { n++; }
</script>
<button onclick={bump}>{n}</button>
""",
    )
    result = extract_svelte(component)
    assert result.get("parse_errors") is None
    labels = _labels(result)
    assert "bump()" in labels
    # Masking keeps offsets, so locations still point at the original lines.
    assert labels["bump()"] == "L4"


def test_extract_svelte_parses_module_and_instance_scripts(tmp_path):
    """Svelte 5 `<script module>` and the instance block are both code."""
    component = _write(
        tmp_path / "src/Both.svelte",
        """<script module>
  export function shared() { return 1; }
</script>
<script>
  function local() { return 2; }
</script>
<p>hi</p>
""",
    )
    result = extract_svelte(component)
    assert result.get("parse_errors") is None
    labels = _labels(result)
    assert "shared()" in labels and "local()" in labels
    assert labels["shared()"] == "L2"
    assert labels["local()"] == "L5"


def test_extract_svelte_lang_ts_parses_type_syntax(tmp_path):
    """`<script lang="ts">` must be parsed with the TS grammar, not JS."""
    component = _write(
        tmp_path / "src/Typed.svelte",
        """<script lang="ts">
  interface Props { year: number }
  let n = $state(1);
  function bump(): void { n++; }
</script>
<button onclick={bump}>{n}</button>
""",
    )
    result = extract_svelte(component)
    assert result.get("parse_errors") is None
    labels = _labels(result)
    assert "Props" in labels
    assert "bump()" in labels


def test_extract_svelte_non_js_script_type_is_not_parsed_as_code(tmp_path):
    """`<script type="application/ld+json">` is data, not statements."""
    component = _write(
        tmp_path / "src/Ld.svelte",
        """<script type="application/ld+json">{ "@type": "Event", "name": "x" }</script>
<script>
  function go() { return 1; }
</script>
<p>hi</p>
""",
    )
    result = extract_svelte(component)
    assert result.get("parse_errors") is None
    assert "go()" in _labels(result)


def test_extract_svelte_static_import_still_resolves(tmp_path):
    """Masking must not cost the imports the regex rescue already recovered."""
    component = _write(
        tmp_path / "src/Imports.svelte",
        """<script>
  import { helper } from "./helper";
</script>
<p>hi</p>
""",
    )
    helper = _write(tmp_path / "src/helper.ts", "export function helper(){}\n")

    result = extract_svelte(component)
    assert _make_id(str(helper)) in _import_targets(result, relation="imports_from")


def test_extract_svelte_dynamic_import_in_template(tmp_path):
    """`{#await import('./X.svelte')}` lives in markup, so the regex pass owns it."""
    component = _write(
        tmp_path / "src/Lazy.svelte",
        """<script>
  let show = true;
</script>
{#await import('./Other.svelte') then Mod}
  <Mod.default />
{/await}
""",
    )
    other = _write(tmp_path / "src/Other.svelte", "<p>o</p>\n")

    result = extract_svelte(component)
    assert _make_id(str(other)) in _import_targets(result, relation="dynamic_import")


def test_extract_svelte_scripts_on_one_line_do_not_merge(tmp_path):
    """Two script bodies on one line must not parse as a single statement."""
    component = _write(
        tmp_path / "src/Inline.svelte",
        "<script>const a = 1</script><script>function b() {}</script>\n",
    )
    result = extract_svelte(component)
    assert result.get("parse_errors") is None
    assert "b()" in _labels(result)


def test_extract_svelte_line_comment_does_not_swallow_next_script(tmp_path):
    """A `//` comment ending one block must not hide a block on the same line."""
    component = _write(
        tmp_path / "src/Commented.svelte",
        "<script module>// shared</script><script>function b() {}</script>\n"
        "<script>function c() {}</script>\n",
    )
    result = extract_svelte(component)
    assert result.get("parse_errors") is None
    labels = _labels(result)
    assert labels.get("b()") == "L1"
    assert labels.get("c()") == "L2"


def test_extract_svelte_comment_after_unterminated_statement(tmp_path):
    """A statement with no `;` before the `//` comment still ends at the block."""
    component = _write(
        tmp_path / "src/Unterminated.svelte",
        "<script module>const a = 1 // shared</script><script>function b() {}</script>\n",
    )
    result = extract_svelte(component)
    assert result.get("parse_errors") is None
    assert _labels(result).get("b()") == "L1"


def test_extract_svelte_unreadable_file_reports_error(tmp_path):
    """A file that cannot be read is reported, not returned as an empty result."""
    result = extract_svelte(tmp_path / "missing" / "Gone.svelte")
    assert result["nodes"] == [] and result["edges"] == []
    assert "error" in result


def test_extract_svelte_markup_only_component_does_not_crash(tmp_path):
    """A `.svelte` file need not have a `<script>` block at all."""
    component = _write(tmp_path / "src/Plain.svelte", "<h1>no script here</h1>\n")
    result = extract_svelte(component)
    assert isinstance(result, dict)
    assert result.get("parse_errors") is None
    assert _import_targets(result, relation="imports_from") == set()
