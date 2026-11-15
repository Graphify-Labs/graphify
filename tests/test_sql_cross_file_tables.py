"""A table referenced from several files is one node, bound to its definition when one exists."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_sql")

from graphify.extract import extract  # noqa: E402


def _project(tmp_path: Path, files: dict[str, str]) -> dict:
    paths = []
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        paths.append(p)
    return extract(paths, root=tmp_path)


def _norm(label: str) -> str:
    return label.replace("[", "").replace("]", "").lower()


def _ids(result: dict, name: str) -> set[str]:
    return {n["id"] for n in result["nodes"] if _norm(n["label"]) == name}


def _read_targets(result: dict, view: str) -> set[str]:
    src = _ids(result, view)
    return {e["target"] for e in result["edges"] if e["source"] in src and e["relation"] == "reads_from"}


VIEWS = {
    "v/a.sql": "CREATE VIEW dbo.VA AS SELECT id FROM {t};\n",
    "v/b.sql": "CREATE VIEW dbo.VB AS SELECT id FROM {t};\n",
}


# bug
@pytest.mark.parametrize("table", ["dbo.Orders", "Orders"])
def test_undefined_table_from_two_files_is_one_node(tmp_path, table):
    r = _project(tmp_path, {k: v.format(t=table) for k, v in VIEWS.items()})
    assert len(_ids(r, table.lower())) == 1
    assert _read_targets(r, "dbo.va") == _read_targets(r, "dbo.vb")


# bug
@pytest.mark.parametrize("table", ["dbo.Orders", "Orders"])
def test_reads_bind_to_table_defined_in_another_file(tmp_path, table):
    files = {"t/tables.sql": f"CREATE TABLE {table} (id INT);\n"}
    files.update({k: v.format(t=table) for k, v in VIEWS.items()})
    r = _project(tmp_path, files)
    defined = _ids(r, table.lower())
    assert len(defined) == 1
    assert _read_targets(r, "dbo.va") == defined
    assert _read_targets(r, "dbo.vb") == defined


# bug
def test_bracket_and_plain_names_across_files_are_one_table(tmp_path):
    r = _project(tmp_path, {
        "t/tables.sql": "CREATE TABLE [dbo].[Orders] (id INT);\n",
        "v/a.sql": "CREATE VIEW dbo.VA AS SELECT id FROM dbo.Orders;\n",
    })
    assert _read_targets(r, "dbo.va") == _ids(r, "dbo.orders")
    assert len(_ids(r, "dbo.orders")) == 1


# guard
def test_same_file_definition_still_binds(tmp_path):
    r = _project(tmp_path, {"a.sql": "CREATE TABLE dbo.Orders (id INT);\nCREATE VIEW dbo.VA AS SELECT id FROM dbo.Orders;\n"})
    assert _read_targets(r, "dbo.va") == _ids(r, "dbo.orders")


# guard
def test_different_schemas_stay_different_tables(tmp_path):
    r = _project(tmp_path, {
        "v/a.sql": "CREATE VIEW dbo.VA AS SELECT id FROM dbo.Orders;\n",
        "v/b.sql": "CREATE VIEW dbo.VB AS SELECT id FROM sales.Orders;\n",
    })
    assert _read_targets(r, "dbo.va").isdisjoint(_read_targets(r, "dbo.vb"))


# guard
def test_sql_read_does_not_bind_to_python_class(tmp_path):
    r = _project(tmp_path, {
        "app/models.py": "class Orders:\n    pass\n",
        "v/a.sql": "CREATE VIEW dbo.VA AS SELECT id FROM Orders;\n",
    })
    py = {n["id"] for n in r["nodes"] if n.get("source_file", "").endswith(".py") and n["label"] == "Orders"}
    assert py
    assert _read_targets(r, "dbo.va").isdisjoint(py)
