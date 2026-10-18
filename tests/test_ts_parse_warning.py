"""#2610/#2599: the #2551 partial-parse warning must not fire on VALID TS/TSX.

tree-sitter-typescript (0.23.x) sets ``has_error`` on tiny, fully-recovered
errors in code ``tsc`` accepts — a ``&`` inside a JSX string attribute, or a
semicolon-less interface member named ``in_*``/``instanceof_*`` — while still
extracting every symbol. Gating the warning on bare ``has_error`` (0.9.37,
#2551) therefore flagged valid files as "syntax errors". The corrected gate
warns only on PLAUSIBLE symbol loss: nothing beyond the file node extracted,
or an ERROR region spanning multiple lines.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files],
                    cache_root=tmp_path / ".cache", parallel=False)
    finally:
        os.chdir(old)
    return r


def _labels(r):
    return {n["label"] for n in r["nodes"]}


def _assert_silent(err):
    assert "syntax errors" not in err
    assert "partially extracted" not in err


def test_tsx_amp_in_jsx_string_attr_is_silent(tmp_path, capsys):
    # `&` inside a JSX string attribute trips a grammar lexer bug: a 4-byte
    # ERROR node covering `&b=2`, has_error=True — but `el` extracts fine and
    # tsc accepts the file. No warning.
    r = _extract(tmp_path, {
        "app.tsx": (
            "declare const Comp: (props: { to: string }) => null;\n"
            'export const el = <Comp to="/p?a=1&b=2" />;\n'
        ),
    })
    assert "el" in _labels(r)
    _assert_silent(capsys.readouterr().err)


def test_ts_interface_member_named_in_prefix_is_silent(tmp_path, capsys):
    # A semicolon-less interface member starting with `in` (`in_workshop`)
    # yields a zero-width MISSING `}` + a 1-byte ERROR, has_error=True — but
    # `I` extracts fine and tsc accepts the file. No warning.
    r = _extract(tmp_path, {
        "types.ts": (
            "interface I { a: number\n"
            " in_workshop: number }\n"
        ),
    })
    assert "I" in _labels(r)
    _assert_silent(capsys.readouterr().err)


def test_ts_generics_as_and_jsx_logical_and_are_silent(tmp_path, capsys):
    # Regression canary: constructs superficially near the lexer bugs —
    # `foo<T>(x)`, an `as` cast, a `<T,>` arrow generic, `&&` in JSX — parse
    # CLEAN (no has_error) and must never warn.
    r = _extract(tmp_path, {
        "generics.ts": (
            "function foo<T>(x: T): T { return x }\n"
            "const y = foo<number>(1);\n"
            "const z = y as number;\n"
        ),
        "arrow.tsx": (
            "const pick = <T,>(x: T) => x;\n"
            "export const view = <div>{true && <span>hi</span>}</div>;\n"
        ),
    })
    assert {"foo()", "pick()", "view"} <= _labels(r)
    _assert_silent(capsys.readouterr().err)


def test_ts_genuinely_broken_file_still_warns(tmp_path, capsys):
    # `function f( {` dissolves the whole parse — nothing beyond the file
    # node extracts. The warning must fire and name the file + first line.
    _extract(tmp_path, {"broken.ts": "function f( {\n"})
    err = capsys.readouterr().err
    assert "syntax errors" in err
    assert "broken.ts" in err
    assert re.search(r"first error at line 1", err)


def test_ts_midfile_breakage_warns_and_keeps_intact_functions(tmp_path, capsys):
    # An unclosed brace between two valid functions produces a multiline
    # ERROR region: the warning fires AND both intact functions extract.
    r = _extract(tmp_path, {
        "midfile.ts": (
            "function alpha() { return 1 }\n"
            "\n"
            "function bad( {\n"
            "  oops;\n"
            "  more;\n"
            "\n"
            "function beta() { return 2 }\n"
        ),
    })
    labels = _labels(r)
    assert "alpha()" in labels
    assert "beta()" in labels
    err = capsys.readouterr().err
    assert "syntax errors" in err
    assert "midfile.ts" in err
