"""Function-valued object properties are captured like shorthand methods.

`{ m(){} }` parses as a `method_definition`, which the generic function
branch captures, but the same API surface written as `{ m: () => {} }` or
`{ m: function(){} }` parses as a `pair`, which was skipped. Two files with
identical runtime exports produced different graphs: the shorthand spelling
kept its symbols, the arrow and function-expression spellings vanished.

These lock the parity: all three spellings of an exported object member emit
the same node shape, bodies are tracked so calls made inside the property
resolve, and the scoping baseline is unchanged (an object bound with
`const api = { ... }` still emits only the const node, matching shorthand).
"""
from __future__ import annotations

from pathlib import Path


def _labels(r):
    return sorted(
        n["label"] for n in r["nodes"] if not n["label"].endswith((".js", ".ts"))
    )


def _extract(tmp_path: Path, name: str, src: str):
    from graphify.extract import extract_js

    p = tmp_path / name
    p.write_text(src, encoding="utf-8")
    return extract_js(p)


def test_arrow_property_matches_shorthand(tmp_path):
    short = _extract(tmp_path, "short.js", "module.exports = { m(){ return 1; } };\n")
    arrow = _extract(tmp_path, "arrow.js", "module.exports = { m: () => 1 };\n")
    assert _labels(short) == ["m()"]
    assert _labels(arrow) == ["m()"]


def test_function_expression_property_matches_shorthand(tmp_path):
    r = _extract(
        tmp_path, "fnexpr.js", "module.exports = { m: function(){ return 1; } };\n"
    )
    assert _labels(r) == ["m()"]


def test_mixed_spellings_all_captured(tmp_path):
    r = _extract(
        tmp_path,
        "mixed.js",
        "module.exports = { m: () => 1, async n(){ return 2; } };\n",
    )
    assert _labels(r) == ["m()", "n()"]


def test_call_argument_object_parity(tmp_path):
    # `register({ m(){} })` already emitted m(); the arrow spelling now matches.
    r = _extract(tmp_path, "callarg.js", "register({ m: () => 1 });\n")
    assert _labels(r) == ["m()"]


def test_property_body_calls_resolve(tmp_path):
    r = _extract(
        tmp_path,
        "calls.js",
        "function helper(){}\nmodule.exports = { run: () => helper() };\n",
    )
    assert _labels(r) == ["helper()", "run()"]
    calls = [e for e in r["edges"] if e["relation"] == "calls"]
    assert any("run" in e["source"] and "helper" in e["target"] for e in calls)


def test_const_object_scoping_baseline_unchanged(tmp_path):
    # Shorthand inside a const object emits only the const node; the arrow
    # spelling must not emit more than the shorthand baseline does.
    short = _extract(tmp_path, "cshort.js", "const api = { m(){ return 1; } };\n")
    arrow = _extract(tmp_path, "carrow.js", "const api = { m: () => 1 };\n")
    assert _labels(short) == ["api"]
    assert _labels(arrow) == ["api"]


def test_parenthesized_function_values_captured(tmp_path):
    r = _extract(tmp_path, "paren.js", "module.exports = { m: (() => 1) };\n")
    assert _labels(r) == ["m()"]
    # a parenthesized non-function value stays out of the graph
    r2 = _extract(tmp_path, "parencall.js", "module.exports = { m: (fn()) };\n")
    assert not [label for label in _labels(r2) if label.endswith("()")]


def test_computed_and_string_keys_still_skipped(tmp_path):
    # Only plain identifier keys are named symbols; computed and string keys
    # stay out of the graph exactly as before.
    r = _extract(
        tmp_path,
        "keys.js",
        'const k = "x";\nmodule.exports = { [k]: () => 1, "quoted-key": () => 2 };\n',
    )
    assert not [label for label in _labels(r) if label.endswith("()")]
