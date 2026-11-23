"""Tests for Oracle APEX 26.1+ APEXlang (.apx) detection and extraction."""
from __future__ import annotations

from pathlib import Path

from graphify.detect import FileType, classify_file
from graphify.extractors.apexlang import DatabaseMirror, extract_apexlang


SAMPLE_PAGE_APX = """\
page 10 (
  name: "Worker Schedule"
  authorizationScheme: @MUST_NOT_BE_PUBLIC_USER

  region "Active Workers" (
    type: report
    sqlQuery: ```sql
      WITH active_scope AS (
        SELECT dept_id FROM hr_departments
      )
      SELECT w.worker_id, w.full_name
        FROM hr_workers w
        JOIN active_scope s ON s.dept_id = w.dept_id
       WHERE w.status = hr_dispatch_pkg.active_status()
    ```
  )

  process "Save Assignment" (
    type: plsql
    plsqlCode: ```plsql
      BEGIN
        INSERT INTO hr_worker_assignments (worker_id, page_id)
        VALUES (:P10_WORKER_ID, 10);
        hr_dispatch_pkg.assign_worker(p_worker_id => :P10_WORKER_ID);
      END;
    ```
  )

  dynamicAction "Open Details" (
    link: "f?p=&APP_ID.:20:&SESSION.::NO::P20_ID:&P10_WORKER_ID."
    listOfValues: @WORKER_STATUS_LOV
  )
)
"""


def test_apx_classified_as_code(tmp_path: Path):
    apx_file = tmp_path / "p00010.apx"
    apx_file.write_text(SAMPLE_PAGE_APX, encoding="utf-8")
    assert classify_file(apx_file) == FileType.CODE


def test_extract_apexlang_components_and_edges(tmp_path: Path):
    app_dir = tmp_path / "apps" / "HR" / "130" / "pages"
    app_dir.mkdir(parents=True)
    apx_file = app_dir / "p00010.apx"
    apx_file.write_text(SAMPLE_PAGE_APX, encoding="utf-8")

    result = extract_apexlang(apx_file)
    assert "error" not in result

    labels = {n["id"]: n["label"] for n in result["nodes"]}
    edges = {(e["source"], e["relation"], e["target"]) for e in result["edges"]}

    page_id = "apex_app_130_page_10"
    region_id = "apex_app_130_page_10_region_active_workers"
    process_id = "apex_app_130_page_10_process_save_assignment"
    da_id = "apex_app_130_page_10_dynamic_action_open_details"

    assert labels[page_id] == "Page 10: Worker Schedule"
    assert labels[region_id] == "Region: Active Workers"
    assert labels[process_id] == "Process: Save Assignment"
    assert labels[da_id] == "Dynamic Action: Open Details"

    assert (page_id, "contains", region_id) in edges
    assert (page_id, "contains", process_id) in edges
    assert (page_id, "contains", da_id) in edges
    assert (page_id, "secured_by", "apex_app_130_authorization_must_not_be_public_user") in edges
    assert (da_id, "navigates_to", "apex_app_130_page_20") in edges
    assert (da_id, "references_component", "apex_app_130_lov_worker_status_lov") in edges

    # SQL / PLSQL edges (CTEs must be excluded from reads_from)
    assert (region_id, "reads_from", "hr_workers") in edges
    assert (region_id, "reads_from", "hr_departments") in edges
    assert not any(tgt == "active_scope" for _s, _r, tgt in edges)
    assert (region_id, "calls", "hr_dispatch_pkg_active_status") in edges
    assert (process_id, "writes_to", "hr_worker_assignments") in edges
    assert (process_id, "calls", "hr_dispatch_pkg_assign_worker") in edges


def test_extract_apexlang_resolves_database_mirror(tmp_path: Path):
    DatabaseMirror.clear_cache()
    tables_dir = tmp_path / "database" / "HR" / "tables"
    pkgs_dir = tmp_path / "database" / "HR" / "packages"
    tables_dir.mkdir(parents=True)
    pkgs_dir.mkdir(parents=True)
    (tables_dir / "HR_WORKERS.sql").write_text('CREATE TABLE "HR"."HR_WORKERS" (ID NUMBER);\n', encoding="utf-8")
    (pkgs_dir / "HR_DISPATCH_PKG_SPEC.sql").write_text(
        'CREATE OR REPLACE PACKAGE "HR"."HR_DISPATCH_PKG" AS FUNCTION ACTIVE_STATUS RETURN VARCHAR2; END;\n',
        encoding="utf-8",
    )

    app_dir = tmp_path / "apps" / "HR" / "130" / "pages"
    app_dir.mkdir(parents=True)
    apx_file = app_dir / "p00010.apx"
    apx_file.write_text(SAMPLE_PAGE_APX, encoding="utf-8")

    result = extract_apexlang(apx_file)
    edges = {(e["source"], e["relation"], e["target"]) for e in result["edges"]}
    region_id = "apex_app_130_page_10_region_active_workers"

    assert (
        region_id,
        "reads_from",
        "database_hr_tables_hr_workers_hr_hr_workers",
    ) in edges
    assert (
        region_id,
        "calls",
        "database_hr_packages_hr_dispatch_pkg_spec",
    ) in edges
