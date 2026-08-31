"""#3154: TypeScript `import(...)` types used in call-expression type arguments.

tree-sitter-typescript misparses `f<typeof import("mod")>()` and
`f<import("mod").Foo>()` as binary comparison expressions (`<` and `>`),
dropping valid symbols declared after the expression when error recovery absorbs
them into the malformed expression statement. Normalizing `import(...)` within
call-expression type arguments to standard type identifiers before AST parsing
keeps extraction complete while preserving source locations and offsets.
"""
from __future__ import annotations

import os
from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path: Path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files],
                    cache_root=tmp_path / ".cache", parallel=False)
    finally:
        os.chdir(old)
    return r


def _labels(r: dict) -> set[str]:
    return {n["label"] for n in r["nodes"]}


def _assert_silent(err: str):
    assert "syntax errors" not in err
    assert "partially extracted" not in err


def test_ts_call_typeof_import_keeps_subsequent_declarations(tmp_path: Path, capsys):
    r = _extract(tmp_path, {
        "main.ts": (
            "function before() {}\n"
            "f<typeof import('mod')>();\n"
            "function after() {}\n"
            "class AfterClass {}\n"
        )
    })
    labels = _labels(r)
    assert "before()" in labels
    assert "after()" in labels
    assert "AfterClass" in labels
    assert "mod" in labels
    _assert_silent(capsys.readouterr().err)


def test_ts_call_import_member_type_keeps_subsequent_declarations(tmp_path: Path, capsys):
    r = _extract(tmp_path, {
        "main.ts": (
            "function before() {}\n"
            "f<import('mod').Foo>();\n"
            "function after() {}\n"
            "class AfterClass {}\n"
        )
    })
    labels = _labels(r)
    assert "before()" in labels
    assert "after()" in labels
    assert "AfterClass" in labels
    assert "mod" in labels
    _assert_silent(capsys.readouterr().err)


def test_tsx_call_typeof_import_keeps_subsequent_declarations(tmp_path: Path, capsys):
    r = _extract(tmp_path, {
        "comp.tsx": (
            "function before() {}\n"
            "f<typeof import('mod')>();\n"
            "function after() {}\n"
            "class AfterWidget {}\n"
            "export const Comp = () => <div>hello</div>;\n"
        )
    })
    labels = _labels(r)
    assert "before()" in labels
    assert "after()" in labels
    assert "AfterWidget" in labels
    assert "Comp()" in labels
    assert "mod" in labels
    _assert_silent(capsys.readouterr().err)


def test_ts_call_generic_controls_remain_clean(tmp_path: Path, capsys):
    r = _extract(tmp_path, {
        "controls.ts": (
            "function before() {}\n"
            "f<string>();\n"
            "f<typeof window>();\n"
            "function after() {}\n"
        )
    })
    labels = _labels(r)
    assert "before()" in labels
    assert "after()" in labels
    _assert_silent(capsys.readouterr().err)


def test_ts_call_import_types_source_locations_are_exact(tmp_path: Path):
    r = _extract(tmp_path, {
        "sample.ts": (
            "function before() {}\n"
            "\n"
            "f<typeof import('mod')>();\n"
            "\n"
            "function after() {}\n"
            "class TargetClass {}\n"
        )
    })
    after_node = next(n for n in r["nodes"] if n["label"] == "after()")
    target_class_node = next(n for n in r["nodes"] if n["label"] == "TargetClass")
    assert after_node["source_location"] == "L5"
    assert target_class_node["source_location"] == "L6"


def test_ts_multiline_import_type_arguments(tmp_path: Path, capsys):
    r = _extract(tmp_path, {
        "multiline.ts": (
            "f<\n"
            "  typeof import(\n"
            "    'mod'\n"
            "  )\n"
            ">();\n"
            "function after() {}\n"
        )
    })
    labels = _labels(r)
    assert "after()" in labels
    assert "mod" in labels
    _assert_silent(capsys.readouterr().err)
