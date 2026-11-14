"""#5169: SQL routine bodies: comma joins and @dblink references."""

from __future__ import annotations

from pathlib import Path
import pytest

pytest.importorskip("tree_sitter_sql")

import importlib.metadata


def _ts_sql_ge(target: tuple[int, ...]) -> bool:
    """Whether the installed tree-sitter-sql grammar is at least *target*."""
    try:
        parts = importlib.metadata.version("tree-sitter-sql").split(".")[:3]
        return tuple(int(x) for x in parts) >= target
    except Exception:
        return False


from graphify.extract import extract_sql
from graphify.extractors.sql import _routine_body_refs

READ = "reads_from"
WRITE = "writes_to"
STRUCTURAL = {"contains"}


def _edges_set(result: dict) -> set[tuple[str, str, str]]:
    label = {n["id"]: n["label"] for n in result["nodes"]}
    return {
        (label.get(e["source"], e["source"]), e["relation"], label.get(e["target"], e["target"]))
        for e in result["edges"]
        if e["relation"] not in STRUCTURAL
    }


def test_issue_5169_repro_comma_join(tmp_path: Path):
    """Oracle-style comma join in a procedure captures all tables, not just the first."""
    p = tmp_path / "t3c.sql"
    p.write_text(
        "CREATE OR REPLACE PROCEDURE p3c IS\n"
        "BEGIN\n"
        "  INSERT INTO hr.t_out SELECT a.id FROM hr.emp a, hr.dept d WHERE a.d = d.id;\n"
        "END;\n"
        "/\n",
        encoding="utf-8",
    )
    r = extract_sql(p)
    edges = _edges_set(r)
    assert ("p3c()", READ, "hr.emp") in edges
    assert ("p3c()", READ, "hr.dept") in edges


def test_issue_5169_repro_dblink(tmp_path: Path):
    """Database link @remote_db suffix is preserved on table references."""
    p = tmp_path / "t3a.sql"
    p.write_text(
        "CREATE OR REPLACE PROCEDURE p3a IS\n"
        "BEGIN\n"
        "  INSERT INTO hr.emp_copy SELECT * FROM hr.emp@remote_db;\n"
        "END;\n"
        "/\n",
        encoding="utf-8",
    )
    r = extract_sql(p)
    edges = _edges_set(r)
    labels = {n["label"] for n in r["nodes"]}
    assert "hr.emp@remote_db" in labels
    assert ("p3a()", READ, "hr.emp@remote_db") in edges


def test_routine_body_refs_comma_join_multi_tables():
    """_routine_body_refs consumes arbitrary comma-separated tables."""
    body = (
        "BEGIN\n"
        "  SELECT a.id, b.name, c.loc\n"
        "  FROM hr.emp a, hr.dept b, hr.locations c\n"
        "  WHERE a.d = b.id AND b.l = c.id;\n"
        "END;\n"
    )
    refs = _routine_body_refs(body)
    tables = [tbl for rel, tbl, _pos in refs if rel == "reads_from"]
    assert tables == ["hr.emp", "hr.dept", "hr.locations"]


def test_routine_body_refs_dblink_read_and_write():
    """_routine_body_refs preserves @dblink on both read and write targets."""
    body = "BEGIN\n  INSERT INTO hr.emp_copy@remote_db\n  SELECT * FROM hr.emp@remote_db;\nEND;\n"
    refs = _routine_body_refs(body)
    pairs = [(r, t) for r, t, _p in refs]
    assert ("writes_to", "hr.emp_copy@remote_db") in pairs
    assert ("reads_from", "hr.emp@remote_db") in pairs


@pytest.mark.skipif(
    _ts_sql_ge((0, 3, 13)),
    reason="tree-sitter-sql >= 0.3.13 does not recover the local write-target node "
    "from the INSERT ... SELECT ERROR node; a pre-existing grammar-recovery gap "
    "unrelated to the dblink fix (#5169).",
)
def test_local_and_remote_tables_remain_distinct_nodes(tmp_path: Path):
    """hr.emp and hr.emp@remote_db are distinct nodes and do not collapse."""
    p = tmp_path / "mixed.sql"
    p.write_text(
        "CREATE OR REPLACE PROCEDURE sync_emp IS\n"
        "BEGIN\n"
        "  INSERT INTO hr.emp SELECT * FROM hr.emp@remote_db;\n"
        "END;\n"
        "/\n",
        encoding="utf-8",
    )
    r = extract_sql(p)
    labels = {n["label"] for n in r["nodes"]}
    assert "hr.emp" in labels
    assert "hr.emp@remote_db" in labels
    edges = _edges_set(r)
    assert ("sync_emp()", READ, "hr.emp@remote_db") in edges


def test_comma_join_with_bracketed_names():
    """Bracketed table names in T-SQL style comma joins are properly handled."""
    body = "SELECT * FROM [dbo].[Orders] o, [dbo].[Payments] p WHERE o.id = p.id;"
    refs = _routine_body_refs(body)
    tables = [tbl for rel, tbl, _pos in refs if rel == "reads_from"]
    assert tables == ["[dbo].[Orders]", "[dbo].[Payments]"]


def test_comma_join_stops_at_keywords():
    """Keywords following a comma join are not matched as table names."""
    body = "SELECT * FROM t1 a, t2 b WHERE a.x = b.x GROUP BY a.y ORDER BY a.z;"
    refs = _routine_body_refs(body)
    tables = [tbl for rel, tbl, _pos in refs if rel == "reads_from"]
    assert tables == ["t1", "t2"]
