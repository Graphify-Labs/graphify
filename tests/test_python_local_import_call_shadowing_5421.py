"""#5421: a Python function-local import shadows a same-named module-level
function/class for the rest of its own body.

``from m import x`` (or ``import x``) written inside ``caller()`` binds ``x``
there for the lexical duration of ``caller``'s own body. A bare ``x()`` call
in that body names the imported symbol, not a same-named module-level
function or class elsewhere in the file -- even when the imported module
cannot be found in the scanned corpus at all, in which case the call must be
left with no target rather than falling back to the coincidentally same-named
local definition.
"""

from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path: Path, files: dict[str, str]) -> dict:
    paths = []
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return extract(paths, cache_root=tmp_path / ".cache", root=tmp_path)


def _calls_from(result: dict, caller_label: str) -> list[dict]:
    """Every `calls` edge whose source node has this label."""
    nodes = {n["id"]: n for n in result["nodes"]}
    return [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and nodes.get(e["source"], {}).get("label") == caller_label
    ]


def test_local_import_of_external_module_suppresses_same_file_call(tmp_path: Path) -> None:
    """The issue's own repro: the imported module is outside the corpus, so
    the call must not fall back to the same-named module-level function."""
    result = _extract(tmp_path, {
        "mod.py": (
            "def main():\n"
            "    pass\n\n\n"
            "def caller():\n"
            "    from absent_external_package import main\n"
            "    main()\n"
        ),
    })
    assert _calls_from(result, "caller()") == []


def test_local_import_of_plain_module_also_suppresses_same_file_call(tmp_path: Path) -> None:
    """`import x` (not just `from m import x`) binds the same way."""
    result = _extract(tmp_path, {
        "mod.py": (
            "def main():\n"
            "    pass\n\n\n"
            "def caller():\n"
            "    import absent_external_package as main\n"
            "    main()\n"
        ),
    })
    assert _calls_from(result, "caller()") == []


def test_local_import_in_one_function_does_not_shadow_a_sibling(tmp_path: Path) -> None:
    """A function-local import's scope is its own body only: a sibling
    function with no import of its own still calls the real local function."""
    result = _extract(tmp_path, {
        "mod.py": (
            "def main():\n"
            "    pass\n\n\n"
            "def caller():\n"
            "    from absent_external_package import main\n"
            "    main()\n\n\n"
            "def other_caller():\n"
            "    main()\n"
        ),
    })
    sibling_calls = _calls_from(result, "other_caller()")
    assert len(sibling_calls) == 1
    nodes = {n["id"]: n for n in result["nodes"]}
    assert nodes[sibling_calls[0]["target"]]["label"] == "main()"


def test_module_level_import_of_same_name_is_unaffected(tmp_path: Path) -> None:
    """Scoped to a FUNCTION-local import only: a module-level import of the
    same name already has its own, separate, correctly-working resolution
    and must not be touched by this guard."""
    result = _extract(tmp_path, {
        "helper.py": "def target():\n    pass\n",
        "mod.py": (
            "from helper import target\n\n\n"
            "def caller():\n"
            "    target()\n"
        ),
    })
    calls = _calls_from(result, "caller()")
    assert len(calls) == 1
    nodes = {n["id"]: n for n in result["nodes"]}
    assert nodes[calls[0]["target"]]["source_file"] == "helper.py"


def test_nested_def_still_shadowed_by_an_outer_functions_local_import(tmp_path: Path) -> None:
    """A closure keeps an outer function's own local import visible to a
    nested def, the same way a captured parameter already is: a miss at the
    nearest enclosing function must keep climbing to the next enclosing
    function instead of stopping and falling back to a same file twin."""
    result = _extract(tmp_path, {
        "mod.py": (
            "def main():\n"
            "    pass\n\n\n"
            "def outer():\n"
            "    from absent_external_package import main\n"
            "    def inner():\n"
            "        return main()\n"
            "    return inner\n"
        ),
    })
    assert _calls_from(result, "inner()") == []


def test_nested_def_shadowed_by_an_outer_plain_import_too(tmp_path: Path) -> None:
    """The closure fix above is form agnostic (`_python_local_import_names`
    already handles both statement types), but a plain `import x`/`import x
    as y` is covered by its own test since it is the surface form namesake
    issue #5421's own follow up singled out separately from the nested
    `from x import y` case."""
    result = _extract(tmp_path, {
        "mod.py": (
            "def main():\n"
            "    pass\n\n\n"
            "def outer():\n"
            "    import absent_external_package as main\n"
            "    def inner():\n"
            "        return main()\n"
            "    return inner\n"
        ),
    })
    assert _calls_from(result, "inner()") == []


def test_a_class_bodys_own_local_import_does_not_shadow_its_methods(tmp_path: Path) -> None:
    """A class body is not part of the closure chain: a method cannot see a
    name its own class bound at class body level without `self`/the class
    name, so the class's own local import must not suppress a bare call in
    one of its methods, which keeps resolving normally."""
    result = _extract(tmp_path, {
        "mod.py": (
            "def target():\n"
            "    pass\n\n\n"
            "class C:\n"
            "    from absent_external_package import target\n\n"
            "    def run(self):\n"
            "        return target()\n"
        ),
    })
    calls = _calls_from(result, ".run()")
    assert len(calls) == 1
    nodes = {n["id"]: n for n in result["nodes"]}
    assert nodes[calls[0]["target"]]["label"] == "target()"
    assert nodes[calls[0]["target"]]["source_file"] == "mod.py"


def test_a_class_bodys_own_direct_code_is_still_shadowed_by_its_own_import(tmp_path: Path) -> None:
    """Class body level code (not inside any method) executes in the class's
    own scope at define time, so it keeps seeing the class's own local
    import exactly like a function body would."""
    result = _extract(tmp_path, {
        "mod.py": (
            "def target():\n"
            "    pass\n\n\n"
            "class C:\n"
            "    from absent_external_package import target\n"
            "    x = target()\n"
        ),
    })
    nodes_by_id = {n["id"]: n for n in result["nodes"]}
    class_ids = {nid for nid, n in nodes_by_id.items() if n.get("label") == "C"}
    assert class_ids
    class_calls = [e for e in result["edges"] if e["relation"] == "calls" and e["source"] in class_ids]
    assert class_calls == []
