"""Tests for `.html` extraction (#1230 — opt-in via `--html-as-code`).

`.html` is DOCUMENT by default: `graphify.detect.classify_file` only routes it
through the local AST path when `html_as_code=True`. `extract_html` mirrors
`extract_vue`/`extract_svelte`/`extract_astro`: mask everything outside inline,
JS-typed `<script>` bodies (preserving newlines so line numbers stay accurate
in the host .html file), then feed the masked source to the plain JS grammar.
"""
from __future__ import annotations

from pathlib import Path

from graphify.detect import CODE_EXTENSIONS, DOC_EXTENSIONS, classify_file, FileType
from graphify.extract import _DISPATCH, extract_html


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _labels(result: dict, *, callable_only: bool = False) -> set[str]:
    return {
        n["label"]
        for n in result.get("nodes", [])
        if not callable_only or n.get("_callable")
    }


def _calls(result: dict) -> set[tuple[str, str]]:
    return {
        (e["source"], e["target"])
        for e in result.get("edges", [])
        if e.get("relation") == "calls"
    }


def test_html_stays_document_by_default():
    """The opt-in contract: no flag, no behavior change (#1230)."""
    assert classify_file(Path("index.html")) == FileType.DOCUMENT
    assert ".html" not in CODE_EXTENSIONS
    assert ".html" in DOC_EXTENSIONS


def test_html_as_code_flag_reclassifies():
    assert classify_file(Path("index.html"), html_as_code=True) == FileType.CODE


def test_html_dispatch_registered():
    """Registered unconditionally (extension-keyed dispatch is inert unless a
    caller actually routes a path here — see detect.classify_file)."""
    assert _DISPATCH[".html"] is extract_html


def test_extract_html_picks_up_inline_script_functions_and_calls(tmp_path):
    page = _write(
        tmp_path / "index.html",
        """<!DOCTYPE html>
<html>
<body>
<script>
function setMode(mode) {
  console.log(mode);
}

function draw(now) {
  setMode(now);
}
</script>
</body>
</html>
""",
    )
    result = extract_html(page)
    labels = _labels(result, callable_only=True)
    assert "setMode()" in labels
    assert "draw()" in labels

    # Line numbers refer to the HOST .html file, not a stripped-down script-only
    # buffer — masking preserves newlines precisely so this holds.
    set_mode = next(n for n in result["nodes"] if n["label"] == "setMode()")
    assert set_mode["source_location"] == "L5"

    calls = _calls(result)
    draw_id = next(n["id"] for n in result["nodes"] if n["label"] == "draw()")
    set_mode_id = set_mode["id"]
    assert (draw_id, set_mode_id) in calls


def test_extract_html_covers_multiple_script_blocks(tmp_path):
    page = _write(
        tmp_path / "multi.html",
        """<html><body>
<script>
function first() { return 1; }
</script>
<p>markup between the two blocks</p>
<script>
function second() { return first(); }
</script>
</body></html>
""",
    )
    result = extract_html(page)
    labels = _labels(result, callable_only=True)
    assert "first()" in labels
    assert "second()" in labels


def test_extract_html_no_script_block_yields_only_file_node(tmp_path):
    """Edge case explicitly called out in #1230: a plain .html with no <script>
    at all must not error, and must not manufacture symbols out of markup."""
    page = _write(tmp_path / "static.html", "<html><body><p>Just text.</p></body></html>\n")
    result = extract_html(page)
    assert len(result["nodes"]) == 1
    assert result["nodes"][0]["label"] == "static.html"
    assert result["edges"] == []


def test_extract_html_external_script_src_contributes_nothing(tmp_path):
    """Edge case explicitly called out in #1230: <script src="..."> has no local
    JS body to parse; it must be treated the same as no script at all, not
    crash and not fabricate a node for the (unfetched) remote file."""
    page = _write(
        tmp_path / "external.html",
        '<html><body><script src="app.js"></script></body></html>\n',
    )
    result = extract_html(page)
    assert len(result["nodes"]) == 1
    assert result["edges"] == []


def test_extract_html_skips_non_js_script_type(tmp_path):
    """A <script type="application/json"> (or similar data blob) is not JS and
    must not be parsed as such — it would either error or, worse, silently
    misparse JSON tokens as bogus JS symbols."""
    page = _write(
        tmp_path / "data.html",
        """<html><body>
<script type="application/json">{"config": {"nested": true}}</script>
<script>
function real() { return 1; }
</script>
</body></html>
""",
    )
    result = extract_html(page)
    labels = _labels(result, callable_only=True)
    assert labels == {"real()"}


def test_extract_html_mixed_inline_and_external_scripts(tmp_path):
    page = _write(
        tmp_path / "mixed.html",
        """<html><body>
<script src="vendor.js"></script>
<script>
function local() { return 1; }
</script>
</body></html>
""",
    )
    result = extract_html(page)
    labels = _labels(result, callable_only=True)
    assert labels == {"local()"}
