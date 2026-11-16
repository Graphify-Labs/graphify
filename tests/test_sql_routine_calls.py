"""#5170: a PL/SQL routine body yields `calls` edges to the routines it invokes."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_sql")

from graphify.extractors.sql import extract_sql  # noqa: E402

SRC = (
    "CREATE OR REPLACE PACKAGE BODY pkg_demo IS\n"
    "  FUNCTION f(x NUMBER) RETURN NUMBER IS\n"
    "  BEGIN\n"
    "    RETURN x + 1;\n"
    "  END f;\n"
    "  PROCEDURE helper IS BEGIN NULL; END helper;\n"
    "  PROCEDURE p IS\n"
    "    v NUMBER;\n"
    "  BEGIN\n"
    "    v := f(1);\n"
    "    helper;\n"
    "    v := hr.g@remote_db(2);\n"
    "    v := other_pkg.h(3);\n"
    "    dbms_output.put_line('x');\n"
    "    v := NVL(v, 0);\n"
    "    INSERT INTO hr.emp_copy(a) SELECT a FROM hr.emp;\n"
    "    EXECUTE IMMEDIATE 'select 1';\n"
    "    EXEC audit_pkg.log_it;\n"
    "  END p;\n"
    "END pkg_demo;\n/\n"
    "CREATE OR REPLACE PROCEDURE top_p IS\n"
    "BEGIN\n"
    "  pkg_demo.p;\n"
    "  top_p(1);\n"
    "END;\n/\n"
)


def _calls(tmp_path: Path, src: str = SRC) -> set[tuple[str, str]]:
    path = tmp_path / "calls.sql"
    path.write_text(src, encoding="utf-8")
    result = extract_sql(path)
    label = {n["id"]: n["label"] for n in result["nodes"]}
    calls = [e for e in result["edges"] if e["relation"] == "calls"]
    assert all(e["confidence"] == "INFERRED" for e in calls)  # name-based, never extracted fact
    return {(label[e["source"]], label[e["target"]]) for e in calls}


def test_calls_edges(tmp_path: Path) -> None:
    assert _calls(tmp_path) == {
        ("pkg_demo.p()", "pkg_demo.f()"),          # a sibling by bare name
        ("pkg_demo.p()", "pkg_demo.helper()"),     # a bare `name;` statement
        ("pkg_demo.p()", "hr.g@remote_db()"),      # a remote call stays remote
        ("pkg_demo.p()", "other_pkg.h()"),         # qualified, defined elsewhere: stub
        ("pkg_demo.p()", "audit_pkg.log_it()"),    # EXEC name
        ("top_p()", "pkg_demo.p()"),               # standalone routine -> package member
    }


def test_no_false_calls(tmp_path: Path) -> None:
    targets = {t for _s, t in _calls(tmp_path)}
    # built-ins, Oracle-supplied packages, INSERT column lists, EXECUTE IMMEDIATE, recursion
    assert targets.isdisjoint({"NVL()", "dbms_output.put_line()", "hr.emp_copy()", "IMMEDIATE()", "top_p()"})


def test_routine_stub_does_not_collide_with_table(tmp_path: Path) -> None:
    src = (
        "CREATE OR REPLACE PROCEDURE p IS\nBEGIN\n"
        "  INSERT INTO hr.thing SELECT 1 FROM dual;\n"
        "  hr.thing(1);\n"
        "END;\n/\n"
    )
    path = tmp_path / "c.sql"
    path.write_text(src, encoding="utf-8")
    labels = [n["label"] for n in extract_sql(path)["nodes"]]
    assert "hr.thing" in labels and "hr.thing()" in labels
