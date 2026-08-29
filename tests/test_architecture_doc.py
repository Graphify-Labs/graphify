"""ARCHITECTURE.md's module table must name symbols that actually exist (#2640).

The "Module responsibilities" table is the entry point for library users, and
AGENTS.md points agents at the docs before the code. It had drifted to document
six functions that do not exist (`detect.collect_files`, `build.build_graph`,
`analyze.analyze`, `report.render_report`, `export.export`,
`serve.start_server`) and to give `extract()` a single-path signature when it
takes a list. Anyone following it wrote code that raised, or -- worse for
`extract()` -- code that ran and silently produced non-canonical ids.

These tests parse the table itself rather than restating it, so adding a row
extends the coverage automatically and renaming a function in the code fails
here until the doc is updated too.
"""
from __future__ import annotations

import importlib
import inspect
import re
from pathlib import Path

import pytest

_ARCHITECTURE = Path(__file__).parent.parent / "ARCHITECTURE.md"

# A table row: | `<module>.py` | <entry points> | <input → output> |
_ROW = re.compile(r"^\|\s*`(\w+)\.py`\s*\|(.*?)\|", re.MULTILINE)
# A function reference inside a cell: `name(...)` or a bare `name`.
_FUNC = re.compile(r"`([a-z_][a-z0-9_]*)(?:\(|`)")


def _documented_symbols() -> list[tuple[str, str]]:
    """(module, function) for every function named in the module table."""
    text = _ARCHITECTURE.read_text(encoding="utf-8")
    start = text.index("## Module responsibilities")
    end = text.index("##", start + 3)
    pairs: list[tuple[str, str]] = []
    for module, cell in _ROW.findall(text[start:end]):
        for func in _FUNC.findall(cell):
            pairs.append((f"graphify.{module}", func))
    return pairs


def test_the_table_was_actually_parsed():
    """Guard the parser itself: a regex that silently matches nothing would make
    every parametrized test below vacuous."""
    pairs = _documented_symbols()
    assert len(pairs) >= 10, f"parsed too few symbols, regex likely broken: {pairs}"
    modules = {m for m, _ in pairs}
    assert {"graphify.extract", "graphify.build", "graphify.serve"} <= modules, modules


@pytest.mark.parametrize("module,func", _documented_symbols())
def test_architecture_table_symbols_exist(module, func):
    mod = importlib.import_module(module)
    assert hasattr(mod, func), (
        f"ARCHITECTURE.md documents {module}.{func}, which does not exist. "
        f"Update the table (or re-export the symbol)."
    )


def test_architecture_documents_extract_as_taking_a_list():
    """`extract(path)` was documented for a function whose first parameter is a
    list; a caller passing one Path gets TypeError: not iterable."""
    from graphify.extract import extract

    params = list(inspect.signature(extract).parameters.values())
    assert params[0].name == "paths", params
    assert "list" in str(params[0].annotation), params[0].annotation

    text = _ARCHITECTURE.read_text(encoding="utf-8")
    assert "`extract(path)`" not in text, "the single-path signature is back"
    assert "extract(paths" in text


def test_architecture_tells_library_callers_to_pass_root():
    """The omitted `root=` is the parameter whose absence yields non-canonical
    ids and source_file values, so the doc must not just name it -- it has to
    say to pass it."""
    from graphify.extract import extract

    root = inspect.signature(extract).parameters["root"]
    assert root.kind is inspect.Parameter.KEYWORD_ONLY, root.kind

    text = _ARCHITECTURE.read_text(encoding="utf-8")
    assert "root=Path" in text, "no worked example passing root"
    assert "Always pass `root`" in text
