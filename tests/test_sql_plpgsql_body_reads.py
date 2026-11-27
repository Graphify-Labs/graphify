"""#5349: a PL/pgSQL body the grammar only partly parses keeps its table reads."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import pytest

pytest.importorskip("tree_sitter_sql")

from graphify.extract import extract_sql

TABLES = "CREATE TABLE users(id int);\nCREATE TABLE orders(id int, uid int);\nCREATE TABLE logs(id int);\n"


def _plpgsql(body: str, returns: str = "SETOF users") -> str:
    return TABLES + f"CREATE FUNCTION f(uid int) RETURNS {returns} AS $$\n{body}\n$$ LANGUAGE plpgsql;\n"


def _body_edges(tmp_path: Path, src: str) -> Counter:
    p = tmp_path / "pg.sql"
    p.write_text(src)
    r = extract_sql(p)
    label = {n["id"]: n["label"] for n in r["nodes"]}
    routines = [n for n in r["nodes"] if n["label"].endswith("()")]
    assert [n["label"] for n in routines] == ["f()"]
    return Counter((label[e["source"]], e["relation"], label.get(e["target"], e["target"]))
                   for e in r["edges"] if e["relation"] in ("reads_from", "writes_to"))


CASES = {
    "return_query": ("BEGIN\n  RETURN QUERY SELECT * FROM users WHERE id = uid;\nEND;",
                     {("f()", "reads_from", "users")}),
    "return_query_join": ("BEGIN\n  RETURN QUERY SELECT u.* FROM users u JOIN orders o ON o.uid = u.id;\nEND;",
                          {("f()", "reads_from", "users"), ("f()", "reads_from", "orders")}),
    "assignment_then_return_query": ("DECLARE n int;\nBEGIN\n  n := 1;\n  RETURN QUERY SELECT * FROM users;\nEND;",
                                     {("f()", "reads_from", "users")}),
    "insert_then_return_query": ("BEGIN\n  INSERT INTO logs VALUES (uid);\n  RETURN QUERY SELECT * FROM users;\nEND;",
                                 {("f()", "reads_from", "users"), ("f()", "writes_to", "logs")}),
    "for_loop_insert": ("DECLARE r record;\nBEGIN\n  FOR r IN SELECT * FROM users LOOP\n    INSERT INTO logs VALUES (r.id);\n  END LOOP;\nEND;",
                        {("f()", "reads_from", "users"), ("f()", "writes_to", "logs")}),
}


@pytest.mark.parametrize("case", CASES)
def test_partly_parsed_plpgsql_body_keeps_reads_and_writes_once(tmp_path, case):
    body, expected = CASES[case]
    got = _body_edges(tmp_path, _plpgsql(body))
    assert set(got) == expected
    assert all(n == 1 for n in got.values()), got


CONTROLS = {
    "dynamic_return_query_execute": ("BEGIN\n  RETURN QUERY EXECUTE 'SELECT * FROM users';\nEND;", "SETOF users", set()),
    "plain_select": ("BEGIN\n  SELECT id FROM users;\nEND;", "int", {("f()", "reads_from", "users")}),
    "perform": ("BEGIN\n  PERFORM id FROM users;\nEND;", "void", {("f()", "reads_from", "users")}),
    "if_insert": ("BEGIN\n  IF uid > 0 THEN\n    INSERT INTO logs VALUES (uid);\n  END IF;\nEND;", "void",
                  {("f()", "writes_to", "logs")}),
    "clean_return": ("BEGIN\n  RETURN 1;\nEND;", "int", set()),
}


@pytest.mark.parametrize("case", CONTROLS)
def test_plpgsql_bodies_that_already_worked_are_unchanged(tmp_path, case):
    body, returns, expected = CONTROLS[case]
    got = _body_edges(tmp_path, _plpgsql(body, returns))
    assert set(got) == expected
    assert all(n == 1 for n in got.values()), got
