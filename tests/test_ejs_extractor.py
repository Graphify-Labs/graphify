"""Extraction coverage for EJS (Embedded JavaScript) templates (#3811, #2511).

A `.ejs` file is HTML carrying `<% %>` scriptlets and inline `<script>` blocks,
so the file as a whole is not JavaScript: fed to the JS grammar it becomes one
top-level ERROR and every symbol inside a scriptlet is lost. `.ejs` sat in
`CODE_EXTENSIONS` with no extractor, so an Express/Node app's views were counted
as code and silently contributed nothing (the #1689 warning).

:func:`extract_ejs` masks the template down to its JS regions — the same
strategy `.svelte`/`.vue`/`.astro` use — parses them with the TS grammar, and
adds the two relationships no JS grammar can see: dynamic `import('./X')` calls
written in a scriptlet, and the EJS `<%- include('partial') %>` composition edge.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import _make_id, extract, extract_ejs


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


def _edges(result: dict, relation: str) -> list[dict]:
    return [e for e in result.get("edges", []) if e.get("relation") == relation]


def test_ejs_registered_as_code():
    from graphify.detect import CODE_EXTENSIONS
    assert ".ejs" in CODE_EXTENSIONS


def test_ejs_in_extractor_dispatch():
    from graphify.extract import _DISPATCH
    assert _DISPATCH.get(".ejs") is extract_ejs


def test_ejs_in_js_language_families():
    # Extraction-time family (cross-file call resolution) and the analyze-time
    # family must both treat a `.ejs` scriptlet as JS.
    from graphify.analyze import _LANG_FAMILY
    from graphify.extract import _LANG_FAMILY_BY_EXT
    assert _LANG_FAMILY_BY_EXT.get(".ejs") == "jsts"
    assert _LANG_FAMILY.get(".ejs") == "js"


def test_ejs_in_resolution_and_hook_sets():
    # `.ejs` is a JS resolve extension (so extensionless requires/includes probe
    # the real template), a cache-bypass suffix (import resolution is
    # corpus-dependent, like the other JS-family SFCs), and a hook source ext
    # (editing a view must re-index the graph).
    from graphify.cli import _HOOK_SOURCE_EXTS
    from graphify.extract import _JS_CACHE_BYPASS_SUFFIXES, _JS_RESOLVE_EXTS
    assert ".ejs" in _JS_RESOLVE_EXTS
    assert ".ejs" in _JS_CACHE_BYPASS_SUFFIXES
    assert ".ejs" in _HOOK_SOURCE_EXTS


def test_extract_ejs_scriptlet_is_not_a_parse_error(tmp_path):
    """Markup is not JS; the scriptlet body is parsed and keeps its line (#3928)."""
    tpl = _write(
        tmp_path / "views" / "page.ejs",
        "<h1><%= title %></h1>\n"
        "<%\n"
        "function greet(name) { return name; }\n"
        "%>\n"
        "<p><%= greet(user) %></p>\n",
    )
    result = extract_ejs(tpl)
    assert result.get("parse_errors") is None
    assert _labels(result)["greet()"] == "L3"


def test_extract_ejs_output_tag_in_inline_script_is_not_a_parse_error(tmp_path):
    """`const x = <%- data %>` inside `<script>` must not break the JS parse."""
    tpl = _write(
        tmp_path / "views" / "inline.ejs",
        "<script>\n"
        "  const data = <%- JSON.stringify(items) %>;\n"
        "  function boot() { return data; }\n"
        "</script>\n",
    )
    result = extract_ejs(tpl)
    assert result.get("parse_errors") is None
    assert "boot()" in _labels(result)


def test_extract_ejs_require_and_import_resolve_to_real_files(tmp_path):
    tpl = _write(
        tmp_path / "views" / "page.ejs",
        "<%\n"
        "const helpers = require('../lib/helpers');\n"
        "import { format } from '../lib/format';\n"
        "%>\n"
        "<p><%= format(x) %></p>\n",
    )
    helpers = _write(tmp_path / "lib" / "helpers.js", "exports.h = {};\n")
    fmt = _write(tmp_path / "lib" / "format.ts", "export function format() {}\n")

    result = extract_ejs(tpl)
    targets = {e["target_file"] for e in result["edges"] if e.get("target_file")}
    assert str(helpers) in targets
    assert str(fmt) in targets


def test_extract_ejs_include_resolves_to_the_real_partial(tmp_path):
    """`<%- include('partials/header') %>` links the view to the partial file.

    This is the relationship an Express view graph is built on (#2511). The
    include is spelled relative to the view without a leading `./` (as in the
    issue's example), and must resolve to the actual `.ejs` file on disk.
    """
    tpl = _write(
        tmp_path / "views" / "inbox.ejs",
        "<%- include('partials/header') %>\n"
        "<p>body</p>\n",
    )
    partial = _write(
        tmp_path / "views" / "partials" / "header.ejs",
        "<header>hi</header>\n",
    )

    result = extract_ejs(tpl)
    includes = _edges(result, "includes")
    assert len(includes) == 1
    assert includes[0]["target"] == _make_id(str(partial))
    assert includes[0]["target_file"] == str(partial)
    assert includes[0]["source_location"] == "L1"


def test_extract_ejs_end_to_end_links_partial_file_node(tmp_path):
    """Through `extract` the stamped include edge repoints at the partial's node."""
    tpl = _write(
        tmp_path / "views" / "inbox.ejs",
        "<%- include('partials/header') %>\n",
    )
    partial = _write(
        tmp_path / "views" / "partials" / "header.ejs",
        "<header>hi</header>\n",
    )

    result = extract([tpl, partial], cache_root=tmp_path, root=tmp_path)
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    targets = {labels.get(e["target"]) for e in _edges(result, "includes")}
    assert "header.ejs" in targets


def test_extract_ejs_unresolved_include_keeps_a_stub(tmp_path):
    """A views-root/bare include that resolves to no file still links something."""
    tpl = _write(
        tmp_path / "views" / "inbox.ejs",
        "<%- include('layouts/app', { title: 'Inbox' }) %>\n",
    )
    result = extract_ejs(tpl)
    includes = _edges(result, "includes")
    assert len(includes) == 1
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    assert labels[includes[0]["target"]] == "layouts/app"


def test_extract_ejs_dynamic_import_in_scriptlet(tmp_path):
    tpl = _write(
        tmp_path / "views" / "lazy.ejs",
        "<% import('./chart.js').then(function(m) { m.init(); }); %>\n",
    )
    chart = _write(tmp_path / "views" / "chart.js", "export function init() {}\n")

    result = extract_ejs(tpl)
    dynamic = _edges(result, "dynamic_import")
    assert len(dynamic) == 1
    assert dynamic[0]["target_file"] == str(chart)


def test_extract_ejs_comment_and_escape_tags_are_not_code(tmp_path):
    """`<%# … %>` is a comment and `<%%` a literal `<%`; neither is a tag."""
    tpl = _write(
        tmp_path / "views" / "quirks.ejs",
        "<%# a comment %>\n"
        "<p>literal <%% not a tag %></p>\n"
        "<% function real() { return 1; } %>\n",
    )
    result = extract_ejs(tpl)
    assert result.get("parse_errors") is None
    labels = _labels(result)
    assert "real()" in labels
    # The escaped literal must not have started a code tag.
    assert not any("not a tag" in label for label in labels)


def test_extract_ejs_markup_only_does_not_crash(tmp_path):
    tpl = _write(tmp_path / "views" / "plain.ejs", "<h1>no script here</h1>\n")
    result = extract_ejs(tpl)
    assert isinstance(result, dict)
    assert result.get("parse_errors") is None
    assert _edges(result, "includes") == []


def test_extract_ejs_unreadable_file_reports_error(tmp_path):
    result = extract_ejs(tmp_path / "missing" / "Gone.ejs")
    assert result["nodes"] == [] and result["edges"] == []
    assert "error" in result


def test_extract_ejs_no_longer_reports_missing_extractor(tmp_path, capsys):
    """The #1689 "no AST extractor" warning must be gone now that `.ejs` is wired."""
    tpl = _write(
        tmp_path / "views" / "page.ejs",
        "<% function f() { return 1; } %>\n<p><%= f() %></p>\n",
    )
    result = extract([tpl], cache_root=tmp_path, root=tmp_path)
    err = capsys.readouterr().err
    assert "no AST extractor" not in err
    assert any(n.get("label") == "page.ejs" for n in result["nodes"])

