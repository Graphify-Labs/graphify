"""Google Apps Script (`.gs`) is treated as JavaScript code.

Apps Script source files are plain JavaScript saved with a `.gs` extension —
that is what `clasp` pulls down and what every Apps Script project in a repo
looks like. The extension was absent from `CODE_EXTENSIONS`, the extractor
`_DISPATCH`, and the JS language-family maps, so an entire Apps Script project
was detected as non-code and contributed nothing to the graph: a build over a
repo whose logic lives in `.gs` returned only its markdown and `appsscript.json`
manifests.

`.gs` is not exclusive to Apps Script (GLSL geometry shaders and Gosu also use
it), so routing is guarded by `_is_apps_script`, which withholds the extractor
when a GLSL or Gosu marker is present rather than force-parsing the file through
the JS grammar. Same shape of gap (and fix) as `.cjs` in
tests/test_cjs_module_extension.py; the sniff mirrors the `.m` Objective-C /
MATLAB split in `_is_objc_source`.
"""
from __future__ import annotations

from pathlib import Path


def _labels(r):
    return [n["label"] for n in r["nodes"]]


def test_gs_registered_as_code():
    from graphify.detect import CODE_EXTENSIONS
    assert ".gs" in CODE_EXTENSIONS


def test_gs_in_extractor_dispatch():
    from graphify.extract import _DISPATCH, extract_js
    assert _DISPATCH.get(".gs") is extract_js


def test_gs_in_js_language_family():
    from graphify.analyze import _LANG_FAMILY
    from graphify.build import _EDGE_LANG_FAMILY
    from graphify.extract import _LANG_FAMILY_BY_EXT
    assert _LANG_FAMILY.get(".gs") == "js"
    assert _EDGE_LANG_FAMILY.get(".gs") == "js"
    assert _LANG_FAMILY_BY_EXT.get(".gs") == "jsts"


def test_gs_in_js_cache_bypass():
    from graphify.extract import _JS_CACHE_BYPASS_SUFFIXES
    assert ".gs" in _JS_CACHE_BYPASS_SUFFIXES


def test_gs_in_hook_source_exts():
    from graphify.cli import _HOOK_SOURCE_EXTS
    assert ".gs" in _HOOK_SOURCE_EXTS


# A representative Apps Script source: global helper functions, a class, a
# container-bound trigger, and calls into the Apps Script service globals.
_GS_SOURCE = (
    "function onOpen() {\n"
    "  SpreadsheetApp.getUi().createMenu('Tools').addToUi();\n"
    "}\n"
    "class VolunteerSheet {\n"
    "  readAll() { return SpreadsheetApp.getActive().getDataRange().getValues(); }\n"
    "}\n"
    "function syncVolunteers() {\n"
    "  const sheet = new VolunteerSheet();\n"
    "  return sheet.readAll();\n"
    "}\n"
)


def _extract(tmp_path: Path, ext: str, source: str = _GS_SOURCE):
    from graphify.extract import extract_js
    f = tmp_path / f"Code{ext}"
    f.write_text(source, encoding="utf-8")
    return extract_js(f)


def test_gs_extracts_like_js(tmp_path):
    # `.gs` must parse identically to the same source saved as `.js` — same
    # node set (class, functions) modulo the file-node label.
    gs = _extract(tmp_path, ".gs")
    js = _extract(tmp_path, ".js")
    assert "error" not in gs
    gs_labels = set(_labels(gs))
    js_labels = set(_labels(js))
    assert any("VolunteerSheet" in label for label in gs_labels), (
        ".gs class declaration missing — file was not parsed as JS"
    )
    assert any("syncVolunteers" in label for label in gs_labels), (
        ".gs function declaration missing — file was not parsed as JS"
    )
    assert {label for label in gs_labels if not label.endswith(".gs")} == {
        label for label in js_labels if not label.endswith(".js")
    }


def test_gs_routed_to_js_extractor(tmp_path):
    from graphify.extract import _get_extractor, extract_js
    f = tmp_path / "Code.gs"
    f.write_text(_GS_SOURCE, encoding="utf-8")
    assert _get_extractor(f) is extract_js


def test_gs_without_service_globals_still_routed(tmp_path):
    # A pure-logic Apps Script helper touches no SpreadsheetApp/DriveApp service
    # at all. Routing must not depend on spotting one.
    from graphify.extract import _get_extractor, extract_js
    f = tmp_path / "Schema.gs"
    f.write_text(
        "function normalizeRow_(row) {\n"
        "  return row.map(function (cell) { return String(cell).trim(); });\n"
        "}\n",
        encoding="utf-8",
    )
    assert _get_extractor(f) is extract_js


def test_glsl_geometry_shader_gs_is_not_extracted(tmp_path):
    # A GLSL geometry shader forced through the JS grammar yields garbage, so it
    # gets no extractor at all (same outcome as MATLAB `.m`).
    from graphify.extract import _get_extractor
    f = tmp_path / "outline.gs"
    f.write_text(
        "#version 330 core\n"
        "layout(triangles) in;\n"
        "layout(line_strip, max_vertices = 6) out;\n"
        "void main() {\n"
        "  gl_Position = gl_in[0].gl_Position;\n"
        "  EmitVertex();\n"
        "  EndPrimitive();\n"
        "}\n",
        encoding="utf-8",
    )
    assert _get_extractor(f) is None


def test_gosu_gs_is_not_extracted(tmp_path):
    from graphify.extract import _get_extractor
    f = tmp_path / "Policy.gs"
    f.write_text(
        "package example.policy\n"
        "uses java.util.ArrayList\n"
        "uses gw.api.database.Query\n"
        "class Policy {\n"
        "  function renew() : String { return \"ok\" }\n"
        "}\n",
        encoding="utf-8",
    )
    assert _get_extractor(f) is None
