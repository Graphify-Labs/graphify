"""Regression tests: TypeScript/JavaScript generator functions as nodes.

Before the fix, `function* g()` (generator_function_declaration) was absent from
`function_types`, so it produced no node, and the expression form
`const h = function*(){}` (generator_function) was absent from the JS
function-value types, so it was never captured either. Generator *methods*
(`*gen()` inside a class) were already covered — they parse as `method_definition`.
"""
from pathlib import Path

from graphify.extract import _file_stem, _make_id, extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _has_node(result: dict, file: str, sym: str) -> bool:
    nid = _make_id(_file_stem(Path(file)), sym)
    return any(n["id"] == nid for n in result["nodes"])


def _contains(result: dict, file: str, sym: str) -> bool:
    tgt = _make_id(_file_stem(Path(file)), sym)
    return any(
        e["target"] == tgt and e["relation"] == "contains"
        for e in result["edges"]
    )


def test_generator_declaration_is_node_ts(tmp_path):
    f = _write(tmp_path / "src" / "g.ts",
               "export function* counter() { yield 1; yield 2; }\n")
    r = extract([f], cache_root=tmp_path)
    assert _has_node(r, "src/g.ts", "counter")
    assert _contains(r, "src/g.ts", "counter")


def test_generator_declaration_is_node_js(tmp_path):
    f = _write(tmp_path / "src" / "g.js",
               "function* gen() { yield 42; }\n")
    r = extract([f], cache_root=tmp_path)
    assert _has_node(r, "src/g.js", "gen")


def test_generator_expression_is_node(tmp_path):
    f = _write(tmp_path / "src" / "h.ts",
               "export const stream = function* () { yield 'a'; };\n")
    r = extract([f], cache_root=tmp_path)
    assert _has_node(r, "src/h.ts", "stream")


def test_generator_body_calls_are_attributed(tmp_path):
    """A call inside a generator's body should be attributed to the generator,
    proving its body is walked (generator is a function boundary like a normal fn)."""
    f = _write(tmp_path / "src" / "g.ts",
               "function helper() {}\n"
               "function* producer() { helper(); yield 1; }\n")
    r = extract([f], cache_root=tmp_path)
    src = _make_id(_file_stem(Path("src/g.ts")), "producer")
    tgt = _make_id(_file_stem(Path("src/g.ts")), "helper")
    assert any(
        e["source"] == src and e["target"] == tgt and e["relation"] == "calls"
        for e in r["edges"]
    ), "call from generator body should resolve to helper()"


def test_async_generator_declaration_is_node(tmp_path):
    f = _write(tmp_path / "src" / "ag.ts",
               "export async function* pages() { yield await Promise.resolve(1); }\n")
    r = extract([f], cache_root=tmp_path)
    assert _has_node(r, "src/ag.ts", "pages")
