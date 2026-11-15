"""GO batch separators without `;` must not swallow the next statement."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_sql")

from graphify.extract import extract_sql  # noqa: E402

TWO_TABLES = "CREATE TABLE dbo.A (id INT){sep}CREATE TABLE dbo.B (id INT){end}"


def _labels(path: Path) -> set[str]:
    return {n["label"].lower() for n in extract_sql(path)["nodes"]}


def _run(tmp_path: Path, text: str) -> set[str]:
    p = tmp_path / "t.sql"
    p.write_bytes(text.encode())
    return _labels(p)


# bug
@pytest.mark.parametrize("sep", [
    "\nGO\n",
    "\ngo\n",
    "\nGO 5\n",
    "\nGO -- next batch\n",
    "\r\nGO\r\n",
    "\n  GO  \n",
])
def test_go_separated_tables_are_both_found(tmp_path, sep):
    labels = _run(tmp_path, TWO_TABLES.format(sep=sep, end="\nGO\n"))
    assert {"dbo.a", "dbo.b"} <= labels


# bug
def test_go_separated_view_reads_its_table(tmp_path):
    p = tmp_path / "t.sql"
    p.write_text("CREATE TABLE dbo.A (id INT)\nGO\nCREATE VIEW dbo.V AS SELECT id FROM dbo.A\nGO\n")
    r = extract_sql(p)
    label = {n["id"]: n["label"].lower() for n in r["nodes"]}
    triples = {(label.get(e["source"]), e["relation"], label.get(e["target"])) for e in r["edges"]}
    assert ("dbo.v", "reads_from", "dbo.a") in triples


# bug
def test_second_table_keeps_its_own_line(tmp_path):
    p = tmp_path / "t.sql"
    p.write_text("CREATE TABLE dbo.A (id INT)\nGO\n\nCREATE TABLE dbo.B (id INT)\nGO\n")
    nodes = {n["label"].lower(): n for n in extract_sql(p)["nodes"]}
    assert "dbo.b" in nodes
    assert nodes["dbo.b"].get("source_location") == "L4"


# guard
def test_semicolon_separated_tables_are_both_found(tmp_path):
    labels = _run(tmp_path, TWO_TABLES.format(sep=";\nGO\n", end=";\nGO\n"))
    assert {"dbo.a", "dbo.b"} <= labels


# guard
def test_go_inside_block_comment_is_not_a_separator(tmp_path):
    text = "CREATE TABLE dbo.A (id INT);\n/*\nGO\nCREATE TABLE dbo.Ghost (id INT)\n*/\n"
    labels = _run(tmp_path, text)
    assert "dbo.a" in labels
    assert "dbo.ghost" not in labels


# guard
def test_column_named_go_is_not_a_separator(tmp_path):
    p = tmp_path / "t.sql"
    p.write_text("CREATE TABLE dbo.A (id INT);\nCREATE VIEW dbo.V AS SELECT a.id,\n go\nFROM dbo.A a;\n")
    r = extract_sql(p)
    label = {n["id"]: n["label"].lower() for n in r["nodes"]}
    triples = {(label.get(e["source"]), e["relation"], label.get(e["target"])) for e in r["edges"]}
    assert ("dbo.v", "reads_from", "dbo.a") in triples


# guard
@pytest.mark.parametrize("prev", ["SET NOCOUNT ON", "SET ANSI_NULLS ON", "SET QUOTED_IDENTIFIER ON", "PRINT 'x' AS"])
def test_go_after_keyword_line_is_a_separator(tmp_path, prev):
    labels = _run(tmp_path, f"{prev}\nGO\nCREATE TABLE dbo.A (id INT)\nGO\nCREATE TABLE dbo.B (id INT)\nGO\n")
    assert {"dbo.a", "dbo.b"} <= labels
