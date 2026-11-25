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


def _write(root: Path, name: str, source: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _calls(result: dict) -> set[tuple[str, str, str]]:
    """Return set of (caller_label, callee_label, target_source_file)."""
    nodes = {n["id"]: n for n in result["nodes"]}
    return {
        (
            nodes[edge["source"]]["label"],
            nodes[edge["target"]]["label"],
            nodes[edge["target"]]["source_file"],
        )
        for edge in result["edges"]
        if edge["relation"] == "calls"
        and edge["source"] in nodes
        and edge["target"] in nodes
    }


def _calls_from(result: dict, caller_label: str) -> list[dict]:
    """Every `calls` edge whose source node has this label."""
    nodes = {n["id"]: n for n in result["nodes"]}
    return [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and nodes.get(e["source"], {}).get("label") == caller_label
    ]


def test_local_import_of_external_module_suppresses_same_file_call(tmp_path: Path) -> None:
    """The issue repro: an absent external package imported locally must not
    fall back to a same-named module-level function."""
    mod = _write(
        tmp_path,
        "mod.py",
        "def main():\n"
        "    pass\n\n\n"
        "def caller():\n"
        "    from absent_external_package import main\n"
        "    main()\n",
    )
    result = extract([mod], root=tmp_path, cache_root=tmp_path / ".cache", parallel=False)
    assert _calls_from(result, "caller()") == []


def test_local_import_of_plain_module_suppresses_same_file_call(tmp_path: Path) -> None:
    """`import x as y` binds the local name the same way."""
    mod = _write(
        tmp_path,
        "mod.py",
        "def main():\n"
        "    pass\n\n\n"
        "def caller():\n"
        "    import absent_external_package as main\n"
        "    main()\n",
    )
    result = extract([mod], root=tmp_path, cache_root=tmp_path / ".cache", parallel=False)
    assert _calls_from(result, "caller()") == []


def test_local_relative_import_resolves_and_does_not_leak_to_sibling(tmp_path: Path) -> None:
    """A local relative import resolves to the imported module for the caller,
    while a sibling function with no import binds to the local definition."""
    _write(tmp_path, "pkg/__init__.py", "")
    helper = _write(tmp_path, "pkg/helper.py", "def target():\n    pass\n")
    mod = _write(
        tmp_path,
        "pkg/mod.py",
        "def target():\n"
        "    pass\n\n\n"
        "def caller():\n"
        "    from .helper import target\n"
        "    target()\n\n\n"
        "def other():\n"
        "    target()\n",
    )
    result = extract([mod, helper], root=tmp_path, cache_root=tmp_path / ".cache", parallel=False)
    calls = _calls(result)
    assert ("caller()", "target()", "pkg/helper.py") in calls
    assert ("other()", "target()", "pkg/mod.py") in calls
    assert ("caller()", "target()", "pkg/mod.py") not in calls
    assert ("other()", "target()", "pkg/helper.py") not in calls


def test_nested_function_inherits_outer_local_import(tmp_path: Path) -> None:
    """A nested function definition inherits local imports from its enclosing function."""
    _write(tmp_path, "pkg/__init__.py", "")
    helper = _write(tmp_path, "pkg/helper.py", "def run():\n    pass\n")
    mod = _write(
        tmp_path,
        "pkg/mod.py",
        "def run():\n"
        "    pass\n\n\n"
        "def outer():\n"
        "    from .helper import run\n"
        "    def inner():\n"
        "        run()\n"
        "    return inner()\n",
    )
    result = extract([mod, helper], root=tmp_path, cache_root=tmp_path / ".cache", parallel=False)
    calls = _calls(result)
    assert ("outer()", "run()", "pkg/helper.py") in calls
    assert not any(target == "run()" and path == "pkg/mod.py" for _, target, path in calls)


def test_nested_function_with_absent_external_import_suppresses_same_file_call(tmp_path: Path) -> None:
    """Enclosing import of absent package suppresses same-file call from nested function."""
    mod = _write(
        tmp_path,
        "mod.py",
        "def main():\n"
        "    pass\n\n\n"
        "def outer():\n"
        "    from absent_external_package import main\n"
        "    def inner():\n"
        "        main()\n"
        "    return inner()\n",
    )
    result = extract([mod], root=tmp_path, cache_root=tmp_path / ".cache", parallel=False)
    assert not any(target.startswith("main") for _, target, _ in _calls(result))


def test_call_before_local_import_binds_to_local_import_not_same_file_def(tmp_path: Path) -> None:
    """In Python, local imports scope the name to the function body regardless of statement line."""
    _write(tmp_path, "pkg/__init__.py", "")
    helper = _write(tmp_path, "pkg/helper.py", "def run():\n    pass\n")
    mod = _write(
        tmp_path,
        "pkg/mod.py",
        "def run():\n"
        "    pass\n\n\n"
        "def caller():\n"
        "    run()\n"
        "    from .helper import run\n",
    )
    result = extract([mod, helper], root=tmp_path, cache_root=tmp_path / ".cache", parallel=False)
    calls = _calls(result)
    assert ("caller()", "run()", "pkg/helper.py") in calls
    assert ("caller()", "run()", "pkg/mod.py") not in calls


def test_repeated_import_in_same_function_respects_statement_order(tmp_path: Path) -> None:
    """When a function re-imports a name, calls between and after resolve by statement order."""
    _write(tmp_path, "pkg/__init__.py", "")
    first = _write(tmp_path, "pkg/first.py", "def run():\n    pass\n")
    second = _write(tmp_path, "pkg/second.py", "def run():\n    pass\n")
    mod = _write(
        tmp_path,
        "pkg/mod.py",
        "def caller():\n"
        "    from .first import run\n"
        "    run()\n"
        "    from .second import run\n"
        "    run()\n",
    )
    result = extract([mod, first, second], root=tmp_path, cache_root=tmp_path / ".cache", parallel=False)
    calls = _calls(result)
    assert ("caller()", "run()", "pkg/first.py") in calls
    assert ("caller()", "run()", "pkg/second.py") in calls


def test_function_local_import_is_not_a_package_reexport(tmp_path: Path) -> None:
    """A function-local import in __init__.py must not be re-exported by the package."""
    init = _write(
        tmp_path,
        "pkg/__init__.py",
        "def setup():\n"
        "    from .helper import run\n"
        "    return run\n",
    )
    helper = _write(tmp_path, "pkg/helper.py", "def run():\n    pass\n")
    consumer = _write(
        tmp_path,
        "app.py",
        "from pkg import run\n\n\n"
        "def main():\n"
        "    run()\n",
    )
    result = extract([consumer, helper, init], root=tmp_path, cache_root=tmp_path / ".cache", parallel=False)
    assert _calls(result) == set()


def test_class_method_local_import_isolation(tmp_path: Path) -> None:
    """Class method local imports are isolated to that method and do not affect sibling methods."""
    mod = _write(
        tmp_path,
        "mod.py",
        "def target():\n"
        "    pass\n\n\n"
        "class Runner:\n"
        "    def caller(self):\n"
        "        from absent_external_package import target\n"
        "        target()\n\n"
        "    def other(self):\n"
        "        target()\n",
    )
    result = extract([mod], root=tmp_path, cache_root=tmp_path / ".cache", parallel=False)
    calls = _calls(result)
    assert (".other()", "target()", "mod.py") in calls
    assert not any(caller == ".caller()" for caller, _, _ in calls)


def test_class_body_absent_import_does_not_suppress_method_call(tmp_path: Path) -> None:
    """A class-body import is not in a method's lexical scope, so methods still resolve module globals."""
    mod = _write(
        tmp_path,
        "mod.py",
        "def target():\n"
        "    pass\n\n\n"
        "class Runner:\n"
        "    from absent_external_package import target\n\n"
        "    def run(self):\n"
        "        target()\n",
    )
    result = extract([mod], root=tmp_path, cache_root=tmp_path / ".cache", parallel=False)
    assert (".run()", "target()", "mod.py") in _calls(result)


def test_class_body_project_import_does_not_redirect_method_call(tmp_path: Path) -> None:
    """A class-body import of a project symbol must not redirect a method's call to module globals."""
    _write(tmp_path, "pkg/__init__.py", "")
    helper = _write(tmp_path, "pkg/helper.py", "def run():\n    pass\n")
    mod = _write(
        tmp_path,
        "pkg/mod.py",
        "def run():\n"
        "    pass\n\n\n"
        "class Runner:\n"
        "    from .helper import run\n\n"
        "    def execute(self):\n"
        "        run()\n",
    )
    result = extract([mod, helper], root=tmp_path, cache_root=tmp_path / ".cache", parallel=False)
    calls = _calls(result)
    assert (".execute()", "run()", "pkg/mod.py") in calls
    assert (".execute()", "run()", "pkg/helper.py") not in calls


def test_nested_function_local_import_does_not_redirect_enclosing_function(tmp_path: Path) -> None:
    """A local import inside a nested function must not redirect calls in the enclosing function."""
    _write(tmp_path, "pkg/__init__.py", "")
    helper = _write(tmp_path, "pkg/helper.py", "def run():\n    pass\n")
    mod = _write(
        tmp_path,
        "pkg/mod.py",
        "def run():\n"
        "    pass\n\n\n"
        "def outer():\n"
        "    def inner():\n"
        "        from .helper import run\n"
        "        run()\n"
        "    run()\n"
        "    return inner\n",
    )
    result = extract([mod, helper], root=tmp_path, cache_root=tmp_path / ".cache", parallel=False)
    calls = _calls(result)
    assert ("outer()", "run()", "pkg/mod.py") in calls
    assert ("outer()", "run()", "pkg/helper.py") not in calls


def test_local_absent_import_shadows_module_level_project_import(tmp_path: Path) -> None:
    """A function-local import of an absent package must not fall back to a module-level import of the same name."""
    helper = _write(tmp_path, "helper.py", "def run():\n    pass\n")
    mod = _write(
        tmp_path,
        "mod.py",
        "from helper import run\n\n\n"
        "def caller():\n"
        "    from absent_external_package import run\n"
        "    run()\n",
    )
    result = extract([mod, helper], root=tmp_path, cache_root=tmp_path / ".cache", parallel=False)
    assert not any(caller == "caller()" for caller, _, _ in _calls(result))
