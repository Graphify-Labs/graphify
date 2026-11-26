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
