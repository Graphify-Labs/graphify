"""#4989: a bare Python builtin must not bind to a same-named package class.

A module that never imports (or otherwise binds) ``NotImplementedError`` is
referring to ``builtins.NotImplementedError``. The cross-file name-only call
resolver used to bind it to any package class of that name anyway, because the
builtin guard was an allowlist that happened to include ``open`` but not the
builtin exception classes. Module-level import evidence from the same file even
promoted the wrong edge to EXTRACTED.

These tests pin both halves of the contract: no edge without a binding, and the
existing EXTRACTED edge when the name really is imported.
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


def _calls(result: dict, source_file: str, target_file: str) -> list[dict]:
    """Every `calls` edge from a function in source_file to target_file."""
    nodes = {n["id"]: n for n in result["nodes"]}
    return [
        e
        for e in result["edges"]
        if e["relation"] == "calls"
        and nodes[e["source"]].get("source_file") == source_file
        and nodes[e["target"]].get("source_file") == target_file
    ]


MINIMAL = {
    "pkg/__init__.py": "",
    "pkg/errors.py": "class NotImplementedError(Exception):\n    pass\n",
}


def test_unimported_builtin_exception_has_no_cross_file_edge(tmp_path: Path) -> None:
    """pkg/a.py never binds the name, so it is the builtin: no edge."""
    result = _extract(tmp_path, {
        **MINIMAL,
        "pkg/a.py": 'def todo():\n    raise NotImplementedError("x")\n',
    })
    assert _calls(result, "pkg/a.py", "pkg/errors.py") == []


def test_imported_builtin_exception_still_resolves_as_extracted(tmp_path: Path) -> None:
    """The control case: an explicit import is real evidence and must survive."""
    result = _extract(tmp_path, {
        **MINIMAL,
        "pkg/b.py": (
            "from pkg.errors import NotImplementedError\n\n\n"
            'def todo2():\n    raise NotImplementedError("x")\n'
        ),
    })
    edges = _calls(result, "pkg/b.py", "pkg/errors.py")
    assert len(edges) == 1
    assert edges[0]["confidence"] == "EXTRACTED"


def test_other_symbol_from_same_module_does_not_certify_builtin(tmp_path: Path) -> None:
    """Importing ValueError from errors.py must not make NotImplementedError an
    EXTRACTED edge to the same file (the real-tree failure mode)."""
    result = _extract(tmp_path, {
        **MINIMAL,
        "pkg/errors.py": (
            "class NotImplementedError(Exception):\n    pass\n\n\n"
            "class ValueError(Exception):\n    pass\n"
        ),
        "pkg/base.py": (
            "from pkg.errors import ValueError\n\n\n"
            'def todo3():\n    raise NotImplementedError("x")\n'
        ),
    })
    assert _calls(result, "pkg/base.py", "pkg/errors.py") == []


def test_plain_module_import_does_not_bind_builtin_name(tmp_path: Path) -> None:
    """`import pkg.errors` does not bind the bare name in the caller module."""
    result = _extract(tmp_path, {
        **MINIMAL,
        "pkg/c.py": (
            "import pkg.errors\n\n\n"
            'def todo4():\n    raise NotImplementedError("x")\n'
        ),
    })
    assert _calls(result, "pkg/c.py", "pkg/errors.py") == []


def test_local_class_with_builtin_name_still_binds_in_file(tmp_path: Path) -> None:
    """A class the file itself defines is the binding: the in-file edge stays."""
    result = _extract(tmp_path, {
        **MINIMAL,
        "pkg/d.py": (
            "class NotImplementedError(Exception):\n    pass\n\n\n"
            'def todo5():\n    raise NotImplementedError("x")\n'
        ),
    })
    nodes = {n["id"]: n for n in result["nodes"]}
    in_file = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and nodes[e["source"]].get("source_file") == "pkg/d.py"
        and nodes[e["target"]].get("source_file") == "pkg/d.py"
        and nodes[e["target"]].get("label") == "NotImplementedError"
    ]
    assert len(in_file) == 1
    assert in_file[0]["confidence"] == "EXTRACTED"
    assert _calls(result, "pkg/d.py", "pkg/errors.py") == []


def test_builtin_exception_passed_by_name_has_no_cross_file_edge(tmp_path: Path) -> None:
    """Indirect by-name dispatch is the same unbound-name case."""
    result = _extract(tmp_path, {
        **MINIMAL,
        "pkg/e.py": (
            "def check(fn):\n    return fn\n\n\n"
            "def todo6():\n    return check(NotImplementedError)\n"
        ),
    })
    nodes = {n["id"]: n for n in result["nodes"]}
    edges = [
        e for e in result["edges"]
        if nodes[e["source"]].get("source_file") == "pkg/e.py"
        and nodes[e["target"]].get("source_file") == "pkg/errors.py"
        and e["relation"] in ("calls", "indirect_call")
    ]
    assert edges == []


def test_non_builtin_unimported_name_keeps_existing_inferred_edge(tmp_path: Path) -> None:
    """The fix is scoped to builtin names; the existing INFERRED heuristic for
    non-builtin bare names is deliberate behavior and must not change."""
    result = _extract(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/errors.py": "class MyError(Exception):\n    pass\n",
        "pkg/f.py": 'def todo7():\n    raise MyError("x")\n',
    })
    edges = _calls(result, "pkg/f.py", "pkg/errors.py")
    assert len(edges) == 1
    assert edges[0]["confidence"] == "INFERRED"
