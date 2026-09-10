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

from graphify.extract import _normalize_ts_import_types, extract


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


def _labelled_edges(r: dict) -> set[tuple[str, str, str]]:
    labels = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (labels.get(e["source"], e["source"]), e["relation"],
         labels.get(e["target"], e["target"]))
        for e in r["edges"]
    }


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


def test_ts_runtime_dynamic_import_between_comparisons_is_not_normalized(tmp_path: Path):
    """#3210: ``<`` and ``>`` in separate semicolon-less statements must not
    make a runtime import look like a call-expression type argument."""
    r = _extract(tmp_path, {
        "main.ts": (
            "async function load(a: number, b: number) {\n"
            "  const flag = a < b\n"
            "  const m = await import('./mod')\n"
            "  const ok = b > (a)\n"
            "  return [flag, m, ok]\n"
            "}\n"
        ),
        "mod.ts": "export const value = 1\n",
    })
    edges = _labelled_edges(r)
    assert ("load()", "imports_from", "mod.ts") in edges
    assert ("main.ts", "dynamic_import", "mod.ts") in edges


def test_ts_spaced_runtime_dynamic_import_keeps_both_edge_granularities(tmp_path: Path):
    """The normalizer and rescue both accept whitespace before ``(``."""
    r = _extract(tmp_path, {
        "main.ts": (
            "async function load(a: number, b: number) {\n"
            "  const flag = a < b\n"
            "  const m = await import ('./mod')\n"
            "  const ok = b > (a)\n"
            "  return [flag, m, ok]\n"
            "}\n"
        ),
        "mod.ts": "export const value = 1\n",
    })
    edges = _labelled_edges(r)
    assert ("load()", "imports_from", "mod.ts") in edges
    assert ("main.ts", "dynamic_import", "mod.ts") in edges


def test_ts_multiple_runtime_imports_between_comparisons_survive(tmp_path: Path):
    r = _extract(tmp_path, {
        "main.ts": (
            "async function load(a: number, b: number) {\n"
            "  const flag = a < b\n"
            "  const m = await import('./mod')\n"
            "  const o = await import ('./other')\n"
            "  const ok = b > (a)\n"
            "  return [flag, m, o, ok]\n"
            "}\n"
        ),
        "mod.ts": "export const value = 1\n",
        "other.ts": "export const other = 2\n",
    })
    edges = _labelled_edges(r)
    for target in ("mod.ts", "other.ts"):
        assert ("load()", "imports_from", target) in edges
        assert ("main.ts", "dynamic_import", target) in edges


def test_ts_nested_comparison_runtime_imports_are_not_masked(tmp_path: Path):
    """A comparison expression inside a call argument is not a generic call.

    tree-sitter can represent ``a < b, import('./mod') > (d)`` as a nested
    call with ``type_arguments`` after a placeholder is inserted. The original
    tree already parses this runtime expression correctly, so it must remain
    untouched in both named-function and arrow-function bodies.
    """
    sources = (
        "async function load(a: number, b: number, d: number) {\n"
        "  const value = foo(a < b, import('./mod') > (d))\n"
        "  return value\n"
        "}\n",
        "const load = async (a: number, b: number, d: number) => {\n"
        "  const value = foo(a < b, import  ('./mod') > (d))\n"
        "  return value\n"
        "}\n",
    )
    for index, source in enumerate(sources):
        case = tmp_path / f"case-{index}"
        r = _extract(case, {
            "main.ts": source,
            "mod.ts": "export const value = 1\n",
        })
        edges = _labelled_edges(r)
        assert ("load()", "imports_from", "mod.ts") in edges
        assert ("main.ts", "dynamic_import", "mod.ts") in edges


def test_ts_comparison_with_import_as_middle_operand_is_not_masked(tmp_path: Path):
    """A valid ``a < import('mod') > (a)`` chain is runtime code, not a type."""
    sources = (
        "function load(a: number) {\n"
        "  const value = a < import('./mod') > (a)\n"
        "  return value\n"
        "}\n",
        "function load(a: number) {\n"
        "  const value = a < import  ('./mod') > (a)\n"
        "  return value\n"
        "}\n",
    )
    for index, source in enumerate(sources):
        case = tmp_path / f"case-{index}"
        r = _extract(case, {
            "main.ts": source,
            "mod.ts": "export const value = 1\n",
        })
        edges = _labelled_edges(r)
        assert ("load()", "imports_from", "mod.ts") in edges
        assert ("main.ts", "dynamic_import", "mod.ts") in edges


def test_ts_normalizer_masks_only_structural_call_type_arguments():
    source = (
        b"const flag = a < b\n"
        b"const m = await import ('./runtime')\n"
        b"const ok = b > (a)\n"
        b"load<typeof import('./types')>();\n"
    )
    normalized = _normalize_ts_import_types(source)
    assert normalized is not None
    assert b"import ('./runtime')" in normalized
    assert b"import('./types')" not in normalized
    assert len(normalized) == len(source)
    assert normalized.count(b"\n") == source.count(b"\n")


def test_ts_normalizer_does_not_mask_import_text_in_literals_or_comments():
    source = (
        b'const text = "load<typeof import(\\\"./text\\\")>()";\n'
        b'// load<typeof import("./comment")>();\n'
        b'load<typeof import("./types")>();\n'
    )
    normalized = _normalize_ts_import_types(source)
    assert normalized is not None
    assert b'import(\\\"./text\\\")' in normalized
    assert b'import("./comment")' in normalized
    assert b'import("./types")' not in normalized


def test_ts_normalizer_scales_linearly_on_large_files():
    """#3359: the match/type-argument-range filters must not be O(matches x ranges).

    A large monorepo file mixes thousands of generic calls (each a
    ``type_arguments`` range) with thousands of ``import(...)`` types. Filtering
    each match by scanning every range made extraction quadratic, so `extract`
    spun at 100% CPU in the regex/scan path and never finished.

    Assert on scaling, not absolute wall-clock, so the test is not
    machine-dependent: doubling the input must not roughly quadruple the time.
    Measure CPU time (``process_time``), not wall-clock (``perf_counter``): under
    a busy full-suite run the process is preempted, and wall-clock would count
    time slices spent scheduled off-CPU — inflating the larger measurement and
    flaking the ratio. CPU time counts only work actually done, so it isolates
    the algorithmic scaling regardless of load.
    """
    import time

    def build(n: int) -> bytes:
        lines = []
        for i in range(n):
            lines.append(f"const a{i} = fn<Foo{i}, Bar{i}>(x);")
            lines.append(f"type T{i} = import('./m{i}').Thing;")
        return "\n".join(lines).encode()

    def timed(n: int) -> float:
        source = build(n)
        start = time.process_time()
        _normalize_ts_import_types(source)
        return time.process_time() - start

    timed(200)  # warm the grammar/parser import off the measured path
    small = min(timed(1000) for _ in range(5))
    large = min(timed(2000) for _ in range(5))

    # Linear work doubles (~2x). Quadratic work quadruples (~4x). A generous
    # 3x ceiling separates the two without being flaky under load.
    assert large < small * 3, (
        f"scaling looks super-linear: {small:.4f}s -> {large:.4f}s "
        f"({large / small:.1f}x for 2x input)"
    )
