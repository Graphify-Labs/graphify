"""CommonJS module extension (`.cjs`) is treated as code.

`.cjs` is the explicit-CommonJS counterpart of `.mjs` (used pervasively in
Electron main/preload scripts and in `"type": "module"` packages that need a
CommonJS escape hatch). The language maps in `build.py` and `extract.py`
already routed `.cjs` to the JS grammar, but the extension was missing from
`CODE_EXTENSIONS`, the extractor `_DISPATCH`, `_LANG_FAMILY`, and the JS
resolution/cache sets — so `.cjs` sources were silently skipped during a build
(detected as non-code and never handed to the JS extractor). These are
regression locks for the extension sets plus an end-to-end extraction proving
`.cjs` parses identically to `.js`.

Same shape of gap (and fix) as `.mts`/`.cts` in
tests/test_typescript_module_extensions.py.
"""
from __future__ import annotations

from pathlib import Path


def _labels(r):
    return [n["label"] for n in r["nodes"]]


def test_cjs_registered_as_code():
    from graphify.detect import CODE_EXTENSIONS
    assert ".cjs" in CODE_EXTENSIONS


def test_cjs_in_extractor_dispatch():
    from graphify.extract import _DISPATCH, extract_js
    assert _DISPATCH.get(".cjs") is extract_js


def test_cjs_in_js_language_family():
    from graphify.analyze import _LANG_FAMILY
    assert _LANG_FAMILY.get(".cjs") == "js"


def test_cjs_in_js_resolution_sets():
    from graphify.extract import _JS_CACHE_BYPASS_SUFFIXES, _JS_RESOLVE_EXTS
    assert ".cjs" in _JS_RESOLVE_EXTS
    assert ".cjs" in _JS_CACHE_BYPASS_SUFFIXES


def test_cjs_in_hook_source_exts():
    from graphify.cli import _HOOK_SOURCE_EXTS
    assert ".cjs" in _HOOK_SOURCE_EXTS


# A representative CommonJS source: require() imports, a class, a function, and
# module.exports — the shape of an Electron main-process script.
_CJS_SOURCE = (
    "const path = require('path');\n"
    "const { app, BrowserWindow } = require('electron');\n"
    "class WindowManager {\n"
    "  open() { return new BrowserWindow(); }\n"
    "}\n"
    "function createWindow() {\n"
    "  const manager = new WindowManager();\n"
    "  return manager.open();\n"
    "}\n"
    "module.exports = { createWindow };\n"
)


def _extract(tmp_path: Path, ext: str):
    from graphify.extract import extract_js
    f = tmp_path / f"main{ext}"
    f.write_text(_CJS_SOURCE, encoding="utf-8")
    return extract_js(f)


def test_cjs_extracts_like_js(tmp_path):
    # `.cjs` must parse identically to the same source saved as `.js` — same
    # node set (require() imports, class, function) modulo the file-node label.
    cjs = _extract(tmp_path, ".cjs")
    js = _extract(tmp_path, ".js")
    assert "error" not in cjs
    cjs_labels = set(_labels(cjs))
    js_labels = set(_labels(js))
    assert any("WindowManager" in label for label in cjs_labels), (
        ".cjs class declaration missing — file was not parsed as JS"
    )
    assert any("createWindow" in label for label in cjs_labels), (
        ".cjs function declaration missing — file was not parsed as JS"
    )
    assert {label for label in cjs_labels if not label.endswith(".cjs")} == {
        label for label in js_labels if not label.endswith(".js")
    }
