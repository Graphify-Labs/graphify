"""#5168: an Oracle package must yield its member procedures and functions."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_sql")

from graphify.extractors.sql import extract_sql  # noqa: E402

BODY = (
    "CREATE OR REPLACE PACKAGE BODY pkg_demo IS\n"
    "  PROCEDURE p IS\n"
    "  BEGIN\n"
    "    INSERT INTO hr.emp_copy SELECT * FROM hr.emp;\n"
    "  END p;\n"
    "  FUNCTION f(x NUMBER) RETURN NUMBER IS\n"
    "  BEGIN\n"
    "    RETURN x + 1;\n"
    "  END f;\n"
    "END pkg_demo;\n/\n"
)
SPEC = (
    "CREATE OR REPLACE PACKAGE pkg_demo IS\n"
    "  PROCEDURE p;\n"
    "  FUNCTION f(x NUMBER) RETURN NUMBER;\n"
    "END pkg_demo;\n/\n"
)


def _graph(tmp_path: Path, src: str, name: str = "pkg.sql"):
    path = tmp_path / name
    path.write_text(src, encoding="utf-8")
    result = extract_sql(path)
    label = {n["id"]: n["label"] for n in result["nodes"]}
    line = {n["label"]: n["source_location"] for n in result["nodes"]}
    edges = sorted(
        (label[e["source"]], e["relation"], label[e["target"]]) for e in result["edges"]
    )
    return line, edges


def test_package_body_members_and_their_tables(tmp_path):
    line, edges = _graph(tmp_path, BODY)

    assert line["pkg_demo"] == "L1"
    assert line["pkg_demo.p()"] == "L2"
    assert line["pkg_demo.f()"] == "L6"
    assert edges == [
        ("pkg.sql", "contains", "pkg_demo"),
        ("pkg_demo", "contains", "pkg_demo.f()"),
        ("pkg_demo", "contains", "pkg_demo.p()"),
        ("pkg_demo.p()", "reads_from", "hr.emp"),
        ("pkg_demo.p()", "writes_to", "hr.emp_copy"),
    ]


def test_package_spec_yields_declared_members(tmp_path):
    line, edges = _graph(tmp_path, SPEC)

    assert edges == [
        ("pkg.sql", "contains", "pkg_demo"),
        ("pkg_demo", "contains", "pkg_demo.f()"),
        ("pkg_demo", "contains", "pkg_demo.p()"),
    ]
    assert line["pkg_demo.p()"] == "L2"


def test_spec_and_body_in_one_file_share_nodes_at_the_definition(tmp_path):
    line, edges = _graph(tmp_path, SPEC + BODY)

    # BODY starts on line 6.
    assert line["pkg_demo.p()"] == "L7"
    assert line["pkg_demo.f()"] == "L11"
    assert edges.count(("pkg_demo", "contains", "pkg_demo.p()")) == 1
    assert ("pkg_demo.p()", "writes_to", "hr.emp_copy") in edges


@pytest.mark.parametrize(
    "head",
    [
        "CREATE PACKAGE BODY hr.pkg AS",
        "CREATE OR REPLACE EDITIONABLE PACKAGE BODY hr.pkg AS",
        'create or replace noneditionable package body "HR"."PKG" as',
        "CREATE PACKAGE BODY IF NOT EXISTS hr.pkg AS",
        "CREATE PACKAGE BODY hr.pkg ACCESSIBLE BY (PROCEDURE hr.caller, PACKAGE hr.other) AS",
    ],
    ids=["plain", "editionable", "quoted-lower", "if-not-exists", "accessible-by"],
)
def test_package_heading_variants(tmp_path, head):
    line, edges = _graph(
        tmp_path,
        head + "\n  PROCEDURE p IS\n  BEGIN\n    DELETE FROM hr.emp;\n  END;\nEND;\n/\n",
    )
    member = [e for e in edges if e[1] == "writes_to"]
    assert len(member) == 1
    assert member[0][0].endswith(".p()") and member[0][2] == "hr.emp"
    assert [label for label in line if label.endswith("()")] == [member[0][0]]
    assert member[0][0].lower().replace('"', "") == "hr.pkg.p()"


def test_nested_blocks_do_not_end_a_member_early(tmp_path):
    line, edges = _graph(
        tmp_path,
        "CREATE OR REPLACE PACKAGE BODY pkg IS\n"
        "  PROCEDURE p(x NUMBER) IS\n"
        "    v NUMBER := CASE WHEN x > 0 THEN 1 ELSE 0 END;\n"
        "  BEGIN\n"
        "    FOR r IN (SELECT id FROM t_loop) LOOP\n"
        "      IF r.id > 0 THEN\n"
        "        BEGIN\n"
        "          INSERT INTO t_inner (id) VALUES (r.id);\n"
        "        EXCEPTION WHEN OTHERS THEN NULL;\n"
        "        END;\n"
        "      END IF;\n"
        "      CASE r.id WHEN 1 THEN NULL; ELSE NULL; END CASE;\n"
        "    END LOOP;\n"
        "    UPDATE t_after SET id = 1;\n"
        "  END p;\n"
        "  PROCEDURE q IS\n"
        "  BEGIN\n"
        "    DELETE FROM t_q;\n"
        "  END q;\n"
        "END pkg;\n/\n",
    )
    assert sorted(e for e in edges if e[0] == "pkg.p()") == [
        ("pkg.p()", "reads_from", "t_loop"),
        ("pkg.p()", "writes_to", "t_after"),
        ("pkg.p()", "writes_to", "t_inner"),
    ]
    assert [e for e in edges if e[0] == "pkg.q()"] == [("pkg.q()", "writes_to", "t_q")]


def test_nested_subprogram_belongs_to_its_member(tmp_path):
    line, edges = _graph(
        tmp_path,
        "CREATE PACKAGE BODY pkg IS\n"
        "  PROCEDURE outer_p IS\n"
        "    PROCEDURE helper IS\n"
        "    BEGIN\n"
        "      INSERT INTO t_helper (id) VALUES (1);\n"
        "    END helper;\n"
        "  BEGIN\n"
        "    helper;\n"
        "    DELETE FROM t_outer;\n"
        "  END outer_p;\n"
        "END pkg;\n/\n",
    )
    assert "pkg.helper()" not in line
    assert sorted(e for e in edges if e[1] == "writes_to") == [
        ("pkg.outer_p()", "writes_to", "t_helper"),
        ("pkg.outer_p()", "writes_to", "t_outer"),
    ]


def test_forward_declaration_and_initialization_block(tmp_path):
    line, edges = _graph(
        tmp_path,
        "CREATE PACKAGE BODY pkg IS\n"
        "  PROCEDURE late;\n"
        "  PROCEDURE early IS\n"
        "  BEGIN\n"
        "    late;\n"
        "  END;\n"
        "  PROCEDURE late IS\n"
        "  BEGIN\n"
        "    DELETE FROM t_late;\n"
        "  END;\n"
        "BEGIN\n"
        "  INSERT INTO t_init (id) VALUES (1);\n"
        "END pkg;\n/\n"
        "DECLARE\n"
        "  PROCEDURE after_pkg IS BEGIN NULL; END;\n"
        "BEGIN\n"
        "  after_pkg;\n"
        "END;\n/\n",
    )
    assert line["pkg.late()"] == "L7"
    assert "pkg.after_pkg()" not in line
    assert [e for e in edges if e[1] != "contains"] == [("pkg.late()", "writes_to", "t_late")]


def test_scan_stops_at_the_package_end(tmp_path):
    line, edges = _graph(
        tmp_path,
        BODY + "CREATE OR REPLACE PROCEDURE standalone IS\nBEGIN\n  DELETE FROM t_s;\nEND;\n/\n",
    )
    assert "standalone()" in line
    assert "pkg_demo.standalone()" not in line
    assert ("standalone()", "writes_to", "t_s") in edges
    assert [e for e in edges if e[0] == "pkg_demo.f()"] == []


def test_package_ddl_in_a_comment_or_string_is_not_recovered(tmp_path):
    line, _ = _graph(
        tmp_path,
        "-- CREATE PACKAGE BODY ghost IS\n"
        "/* CREATE PACKAGE BODY ghost2 IS PROCEDURE p IS BEGIN NULL; END; END; */\n"
        "SELECT 'CREATE PACKAGE ghost3 IS PROCEDURE p; END;' FROM dual;\n"
        + BODY,
    )
    assert not any(label.startswith("ghost") for label in line)
    assert "pkg_demo.p()" in line


def test_package_named_body_is_a_spec(tmp_path):
    line, _ = _graph(tmp_path, "CREATE PACKAGE body IS\n  PROCEDURE p;\nEND body;\n/\n")
    assert "body.p()" in line


def test_select_into_a_variable_is_not_a_write(tmp_path):
    _, edges = _graph(
        tmp_path,
        "CREATE PACKAGE BODY pkg IS\n"
        "  FUNCTION f RETURN NUMBER IS\n"
        "    n NUMBER;\n"
        "  BEGIN\n"
        "    SELECT COUNT(*) INTO n FROM hr.emp;\n"
        "    INSERT INTO hr.log (id) VALUES (n) RETURNING id INTO n;\n"
        "    RETURN n;\n"
        "  END f;\n"
        "END pkg;\n/\n",
    )
    assert [e for e in edges if e[1] != "contains"] == [
        ("pkg.f()", "reads_from", "hr.emp"),
        ("pkg.f()", "writes_to", "hr.log"),
    ]


def test_call_spec_member_has_no_block_to_close(tmp_path):
    # `AS LANGUAGE ...` defines a member with no BEGIN/END.
    line, edges = _graph(
        tmp_path,
        "CREATE PACKAGE BODY pkg AS\n"
        "  FUNCTION h(p VARCHAR2) RETURN NUMBER AS LANGUAGE JAVA NAME 'H.h(java.lang.String) return int';\n"
        "  PROCEDURE overloaded(a NUMBER) IS BEGIN DELETE FROM t1; END;\n"
        "  PROCEDURE overloaded(a VARCHAR2) IS BEGIN DELETE FROM t2; END;\n"
        "END pkg;\n/\n"
        "CREATE TABLE after_pkg (id NUMBER);\n",
    )
    assert line["pkg.h()"] == "L2"
    assert [e for e in edges if e[0] == "pkg.overloaded()"] == [
        ("pkg.overloaded()", "writes_to", "t1"),
        ("pkg.overloaded()", "writes_to", "t2"),
    ]
    assert ("pkg.sql", "contains", "after_pkg") in edges
