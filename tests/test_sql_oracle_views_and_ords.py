"""Tests for Oracle EDITIONABLE/FORCE VIEW recovery and ORDS REST handler extraction."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_sql")

from graphify.extractors.sql import extract_sql  # noqa: E402


ORACLE_VIEW = """\
CREATE OR REPLACE FORCE EDITIONABLE VIEW "HR"."EMP_DEPT_V" ("EMP_ID", "DEPT_NAME") AS
  SELECT e.emp_id, d.dept_name
    FROM "HR"."EMPLOYEES" e
    JOIN "HR"."DEPARTMENTS" d ON d.dept_id = e.dept_id;
"""

ORDS_EXPORT = """\
DECLARE
  l_roles     OWA.VC_ARR;
  l_modules   OWA.VC_ARR;
  l_patterns  OWA.VC_ARR;
BEGIN
  ORDS.DEFINE_MODULE(
      p_module_name    => 'hr_api',
      p_base_path      => '/hr-public/',
      p_items_per_page => 25,
      p_status         => 'PUBLISHED',
      p_comments       => NULL);

  ORDS.DEFINE_TEMPLATE(
      p_module_name    => 'hr_api',
      p_pattern        => 'employees/transfer');

  ORDS.DEFINE_HANDLER(
      p_module_name    => 'hr_api',
      p_pattern        => 'employees/transfer',
      p_method         => 'POST',
      p_source_type    => 'plsql/block',
      p_mimes_allowed  => 'application/json',
      p_comments       => NULL,
      p_source         =>
'BEGIN
   INSERT INTO hr.transfer_audit (emp_id)
   SELECT e.emp_id FROM hr.employees e WHERE e.active = ''Y'';
END;');

  COMMIT;
END;
/
"""


def _graph(tmp_path: Path, name: str, src: str):
    path = tmp_path / name
    path.write_text(src, encoding="utf-8")
    result = extract_sql(path)
    label = {n["id"]: n["label"] for n in result["nodes"]}
    edges = sorted(
        (label[e["source"]], e["relation"], label[e["target"]])
        for e in result["edges"]
    )
    return sorted(label.values()), edges


@pytest.mark.parametrize(
    "modifiers",
    [
        "FORCE EDITIONABLE ",
        "NOFORCE EDITIONABLE ",
        "EDITIONABLE ",
        "NONEDITIONABLE ",
        "FORCE ",
    ],
)
def test_oracle_view_modifiers_recover_view_and_reads_from(tmp_path, modifiers):
    ddl = ORACLE_VIEW.replace("FORCE EDITIONABLE ", modifiers)
    labels, edges = _graph(tmp_path, "emp_dept_v.sql", ddl)

    assert '"HR"."EMP_DEPT_V"' in labels
    assert ('"HR"."EMP_DEPT_V"', "reads_from", '"HR"."EMPLOYEES"') in edges
    assert ('"HR"."EMP_DEPT_V"', "reads_from", '"HR"."DEPARTMENTS"') in edges
    # Column list identifiers before AS must not be treated as table references.
    assert not any(tgt in ('"EMP_ID"', '"DEPT_NAME"') for _s, _r, tgt in edges)


def test_editionable_table_recovery_when_file_has_error(tmp_path):
    ddl = (
        'CREATE EDITIONABLE TABLE "HR"."AUDIT_LOG" ("ID" NUMBER);\n'
        "CREATE OR REPLACE EDITIONABLE PROCEDURE hr.p IS BEGIN NULL; END;\n/\n"
    )
    labels, edges = _graph(tmp_path, "tbl.sql", ddl)

    assert '"HR"."AUDIT_LOG"' in labels
    assert ("tbl.sql", "contains", '"HR"."AUDIT_LOG"') in edges


def test_ords_define_module_and_handler_extraction(tmp_path):
    labels, edges = _graph(tmp_path, "ords.sql", ORDS_EXPORT)

    assert "ORDS POST /hr-public/employees/transfer" in labels
    assert ("ords.sql", "contains", "ORDS POST /hr-public/employees/transfer") in edges
    assert ("ORDS POST /hr-public/employees/transfer", "reads_from", "hr.employees") in edges
    assert ("ORDS POST /hr-public/employees/transfer", "writes_to", "hr.transfer_audit") in edges


def test_ords_ignores_commented_out_calls_and_supports_q_quotes(tmp_path):
    ddl = """\
DECLARE
BEGIN
  /*
  ORDS.DEFINE_MODULE(p_module_name => 'ghost_api', p_base_path => '/ghost/');
  ORDS.DEFINE_HANDLER(
      p_module_name => 'ghost_api',
      p_pattern     => 'fake',
      p_method      => 'DELETE',
      p_source      => 'DELETE FROM hr.employees;');
  */
  ORDS.DEFINE_MODULE(p_module_name => 'hr_api', p_base_path => '/hr-public/');
  ORDS.DEFINE_HANDLER(
      p_module_name => 'hr_api',
      p_pattern     => 'roster',
      p_method      => 'GET',
      p_source      => q'[SELECT * FROM hr.roster WHERE status = 'ACTIVE']');
END;
/
"""
    labels, edges = _graph(tmp_path, "ords_q.sql", ddl)

    assert "ORDS GET /hr-public/roster" in labels
    assert ("ORDS GET /hr-public/roster", "reads_from", "hr.roster") in edges
    assert not any("ghost" in lbl or "fake" in lbl for lbl in labels)

