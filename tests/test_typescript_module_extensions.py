"""TypeScript module extensions (`.mts` / `.cts`) are treated as code.

`.mts` (ESM) and `.cts` (CommonJS) are the TypeScript counterparts of `.mjs` /
`.cjs`. They were missing from the code-extension detection set and the JS/TS
language maps, so `.mts` / `.cts` sources were silently skipped during a build
(detected as non-code and never handed to the JS/TS extractor). These are
regression locks for the four extension sets plus an end-to-end extraction proving
the files route to the same grammar as `.ts`.
"""
from __future__ import annotations

from pathlib import Path


def _labels(r):
    return [n["label"] for n in r["nodes"]]


def test_mts_cts_registered_as_code():
    from graphify.detect import CODE_EXTENSIONS
    assert ".mts" in CODE_EXTENSIONS
    assert ".cts" in CODE_EXTENSIONS


def test_mts_cts_in_js_language_family():
    from graphify.analyze import _LANG_FAMILY
    assert _LANG_FAMILY.get(".mts") == "js"
    assert _LANG_FAMILY.get(".cts") == "js"


def test_mts_cts_in_js_resolution_sets():
    from graphify.extract import _JS_CACHE_BYPASS_SUFFIXES, _JS_RESOLVE_EXTS
    assert ".mts" in _JS_RESOLVE_EXTS
    assert ".cts" in _JS_RESOLVE_EXTS
    assert ".mts" in _JS_CACHE_BYPASS_SUFFIXES
    assert ".cts" in _JS_CACHE_BYPASS_SUFFIXES


# A source with TypeScript-only syntax (a `type` alias + an `interface`) — these
# only parse under the TypeScript grammar, so they prove `.mts`/`.cts` route to it
# (the plain JS grammar would silently drop them).
_TS_SOURCE = (
    "export type Mode = 'a' | 'b';\n"
    "export interface Options { mode: Mode; retries: number; }\n"
    "export function greet(name: string): string { return `hi ${name}`; }\n"
    "export class Widget { render(): void {} }\n"
)


def _extract(tmp_path: Path, ext: str):
    from graphify.extract import extract_js
    f = tmp_path / f"widget{ext}"
    f.write_text(_TS_SOURCE, encoding="utf-8")
    return extract_js(f)


def test_mts_uses_the_typescript_grammar(tmp_path):
    # `.mts` must parse identically to `.ts` — same node set, including the TS-only
    # `type`/`interface` declarations that the plain JS grammar cannot see.
    mts = set(_labels(_extract(tmp_path, ".mts")))
    ts = set(_labels(_extract(tmp_path, ".ts")))
    assert "error" not in _extract(tmp_path, ".mts")
    assert any("Mode" in label for label in mts), "TS `type` alias missing → .mts fell back to the JS grammar"
    assert any("Options" in label for label in mts), "TS `interface` missing → .mts fell back to the JS grammar"
    # Full parity with the .ts equivalent (module the differing file-node label).
    assert {label for label in mts if not label.endswith(".mts")} == {
        label for label in ts if not label.endswith(".ts")
    }


def test_cts_uses_the_typescript_grammar(tmp_path):
    cts = set(_labels(_extract(tmp_path, ".cts")))
    ts = set(_labels(_extract(tmp_path, ".ts")))
    assert any("Mode" in label for label in cts), "TS `type` alias missing → .cts fell back to the JS grammar"
    assert any("Options" in label for label in cts), "TS `interface` missing → .cts fell back to the JS grammar"
    assert {label for label in cts if not label.endswith(".cts")} == {
        label for label in ts if not label.endswith(".ts")
    }


def test_uppercase_typescript_extensions_use_typescript_grammar(tmp_path):
    for ext in (".TS", ".TSX", ".MTS", ".CTS"):
        labels = _labels(_extract(tmp_path, ext))
        assert any("Mode" in label for label in labels), f"TS `type` alias missing for {ext}"
        assert any("Options" in label for label in labels), f"TS `interface` missing for {ext}"


def test_mts_cts_route_to_extract_js():
    from graphify.extract import _DISPATCH, extract_js
    assert _DISPATCH.get(".mts") is extract_js
    assert _DISPATCH.get(".cts") is extract_js
