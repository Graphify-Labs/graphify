"""Regression tests for graphify.detect.xlsx_extract_structure.

xlsx_extract_structure reads an .xlsx file and emits a graphify-shaped
nodes/edges dict describing its sheets, named tables, and column
headers. The function was previously broken by a ``_re.sub`` typo
(security finding F-035) — the wrong module name leaked into the
helper, which would have raised ``NameError`` the first time the
xlsx code path was wired into the dispatcher.

The fix landed in commit 67eb547 (extraction). At the time of this
test, the xlsx code path is still behind a feature flag and not
called from the normal `graphify update` flow, so the regression
risk is that a future cleanup of the still-buggy path could quietly
revert the typo fix. These tests pin the correct behaviour:

- happy path: a small .xlsx with one sheet and headers produces a
  non-empty nodes/edges dict with a sheet node, a header node, and
  a contains edge between them
- the F-035 invariant: the function references the top-level ``re``
  module, not the broken ``_re`` alias

The office extra is optional, so we ``pytest.importorskip("openpyxl")``
to skip cleanly on lean installs.
"""
from __future__ import annotations

import pytest

from graphify import detect

openpyxl = pytest.importorskip("openpyxl")


def _build_sample_workbook(path) -> None:
    """Write a small .xlsx with one named ListObject table.

    xlsx_extract_structure only emits column-header nodes for sheets
    that have a named Excel table (ListObject) — the no-table fallback
    path in the function is dead code in practice, because every
    openpyxl Worksheet has a ``tables`` attribute (empty dict) so the
    ``if hasattr(ws, "tables")`` check always succeeds and the
    ``else`` branch never runs. Building a named table exercises the
    header-emitting code path for real.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Customers"
    ws.append(["name", "email", "plan"])
    ws.append(["Alice", "alice@example.com", "pro"])
    ws.append(["Bob", "bob@example.com", "free"])
    table = openpyxl.worksheet.table.Table(
        displayName="customers", ref="A1:C4"
    )
    ws.add_table(table)
    wb.save(str(path))


def test_xlsx_extract_structure_returns_graphify_shaped_dict(tmp_path):
    """Happy path: a small workbook produces a non-empty nodes/edges dict.

    Pins the contract that the function returns the standard
    ``{"nodes": [...], "edges": [...]}`` shape consumed by the rest
    of the extract pipeline, with at least one sheet node and one
    column-header node connected by a contains edge.
    """
    path = tmp_path / "sample.xlsx"
    _build_sample_workbook(path)

    result = detect.xlsx_extract_structure(path)

    assert "nodes" in result and "edges" in result, (
        "result must use the graphify nodes/edges dict shape; got "
        f"keys={list(result)}"
    )
    assert result["nodes"], "no nodes extracted from a real workbook"
    assert result["edges"], "no edges extracted from a real workbook"

    labels = [n["label"] for n in result["nodes"]]
    assert any("Customers" in label for label in labels), (
        f"expected the sheet name in a node label, got {labels!r}"
    )
    assert any(label in {"name", "email", "plan"} for label in labels), (
        f"expected at least one column header in node labels, got {labels!r}"
    )

    relations = {e["relation"] for e in result["edges"]}
    assert "contains" in relations, (
        f"expected a 'contains' edge between sheet and columns, got {relations!r}"
    )


def test_xlsx_extract_structure_does_not_reference_missing_re_alias():
    """F-035 invariant: the function uses the top-level ``re`` module.

    A previous version had ``stem = _re.sub(...)`` (note the leading
    underscore) which would raise ``NameError`` if the xlsx code path
    were ever wired into the dispatcher. Pin the source so a future
    re-introduction of the typo is caught by the test suite.
    """
    # Read the detect.py module source and check the xlsx code path
    # specifically — not just any "re" reference in the file.
    src = open(detect.__file__.replace("__init__.py", "detect.py")).read()

    # Isolate the body of xlsx_extract_structure so other functions in
    # detect.py that legitimately talk about ``_re`` (e.g. regex
    # helpers named ``_re_*``) don't trip the assertion.
    start = src.find("def xlsx_extract_structure(")
    assert start != -1, "xlsx_extract_structure not found in detect.py"
    # Find the next top-level ``def`` after this one — that's the end
    # of xlsx_extract_structure.
    next_def = src.find("\ndef ", start + 1)
    body = src[start:next_def if next_def != -1 else None]

    # Strip out comments before searching — the F-035 history comment
    # in the function body legitimately references the old typo name
    # and shouldn't trip the assertion. The bug we care about is a
    # *code* reference, not a doc/comment mention.
    code_lines = [
        line for line in body.splitlines()
        if line.lstrip().startswith("#") is False
    ]
    code_only = "\n".join(code_lines)

    assert "_re.sub" not in code_only, (
        "F-035 regression: xlsx_extract_structure still references "
        "`_re.sub` (the undefined alias) in executable code. Use the "
        "top-level `re` module instead — see commit 67eb547 for the "
        "original fix."
    )
    # And the positive invariant: the body uses ``re.sub`` somewhere
    # (the _nid helper definition alone proves that). Just sanity-check
    # the top-level re module is the one being used.
    assert "re.sub" in code_only, (
        "sanity check: the function body should reference `re.sub` "
        "(the _nid helper is defined with it)"
    )
