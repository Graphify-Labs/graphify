"""Swift 5.9 macro declarations must be extracted, not silently dropped.

`macro stringify(...) = #externalMacro(...)` parses as a `macro_declaration`,
and a freestanding call `#stringify(...)` parses as a `macro_invocation` —
neither of which is a `function_declaration`/`call_expression`. Before the fix
the whole macro declaration (and every `#name` call site) was dropped: the
symbol never appeared in the graph. A `macro_declaration` has no `name` field
(the name is a bare `simple_identifier`, covered by Swift's
`name_fallback_child_types`).
"""
from pathlib import Path

from graphify.extract import extract


def _labels(r):
    return [n["label"] for n in r["nodes"]]


def _calls(r):
    id_to_label = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (id_to_label.get(e["source"]), id_to_label.get(e["target"]))
        for e in r["edges"]
        if e["relation"] == "calls"
    }


def test_freestanding_macro_declaration_is_extracted(tmp_path):
    (tmp_path / "m.swift").write_text(
        '@freestanding(expression)\n'
        'macro stringify<T>(_ value: T) -> (T, String) = '
        '#externalMacro(module: "M", type: "S")\n'
    )
    r = extract([tmp_path / "m.swift"], cache_root=tmp_path, parallel=False)
    assert any("stringify" in l for l in _labels(r)), (
        "macro declaration was dropped"
    )
    # The generic type parameter `T` must not leak as a sourceless god node.
    assert not any(e.get("target") == "t" for e in r["edges"])


def test_attached_macro_declaration_is_extracted(tmp_path):
    (tmp_path / "m.swift").write_text(
        '@attached(member)\n'
        'macro AddCompletion() = #externalMacro(module: "M", type: "AddCompletionMacro")\n'
    )
    r = extract([tmp_path / "m.swift"], cache_root=tmp_path, parallel=False)
    assert any("AddCompletion" in l for l in _labels(r))


def test_freestanding_macro_invocation_resolves_to_declaration(tmp_path):
    (tmp_path / "m.swift").write_text(
        'macro stringify<T>(_ value: T) -> (T, String) = '
        '#externalMacro(module: "M", type: "S")\n'
        '\n'
        'func use() {\n'
        '  let x = #stringify(1 + 1)\n'
        '}\n'
    )
    r = extract([tmp_path / "m.swift"], cache_root=tmp_path, parallel=False)
    assert ("use()", "stringify()") in _calls(r), (
        "freestanding macro call #stringify did not resolve to the macro"
    )


def test_call_inside_macro_argument_still_resolves(tmp_path):
    # Recursing into a macro_invocation's arguments must still find ordinary
    # calls: `#stringify(helper())` keeps `use() -> helper()`.
    (tmp_path / "m.swift").write_text(
        'macro stringify<T>(_ value: T) -> (T, String) = '
        '#externalMacro(module: "M", type: "S")\n'
        '\n'
        'func helper() -> Int { return 1 }\n'
        'func use() { let x = #stringify(helper()) }\n'
    )
    r = extract([tmp_path / "m.swift"], cache_root=tmp_path, parallel=False)
    calls = _calls(r)
    assert ("use()", "stringify()") in calls
    assert ("use()", "helper()") in calls
