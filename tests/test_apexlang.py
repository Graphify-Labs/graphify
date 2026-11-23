"""Tests for Oracle APEX 26.1+ APEXlang (.apx) detection and extraction."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from graphify.build import build
from graphify.detect import FileType, classify_file
from graphify.extract import extract
from graphify.extractors.apexlang import extract_apexlang


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

    # SQL / PLSQL edges (CTEs must be excluded from all nodes and edges)
    dependencies = {
        (source, relation, labels[target])
        for source, relation, target in edges if relation in {"reads_from", "writes_to", "calls"}
    }
    assert (region_id, "reads_from", "HR_WORKERS") in dependencies
    assert (region_id, "reads_from", "HR_DEPARTMENTS") in dependencies
    assert not any(
        "active_scope" in str(n.get("id", "")).casefold()
        or "active_scope" in str(n.get("label", "")).casefold()
        for n in result["nodes"]
    )
    assert all(
        "active_scope" not in endpoint.casefold()
        for source, _, target in edges
        for endpoint in (source, target)
    )
    assert (region_id, "calls", "HR_DISPATCH_PKG.ACTIVE_STATUS") in dependencies
    assert (process_id, "writes_to", "HR_WORKER_ASSIGNMENTS") in dependencies
    assert (process_id, "calls", "HR_DISPATCH_PKG.ASSIGN_WORKER") in dependencies


def test_extract_apexlang_app_properties_and_malformed_input(tmp_path: Path):
    app_file = tmp_path / "apps" / "HR" / "130" / "application.apx"
    app_file.parent.mkdir(parents=True)
    app_file.write_text(
        'app 130 (\n'
        '  name: "HR Portal"\n'
        '  authentication "Custom Auth" (\n'
        '    authFunctionName: "hr_auth_pkg.authenticate"\n'
        '  )\n'
        '  region "Summary" (\n'
        '    tableName: "HR_EMP_SUMMARY"\n'
        '  )\n'
        ')\n',
        encoding="utf-8",
    )

    result = extract_apexlang(app_file)
    assert "error" not in result
    edges = {(e["source"], e["relation"], e["target"]) for e in result["edges"]}
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    dependencies = {
        (source, relation, labels[target])
        for source, relation, target in edges if relation in {"reads_from", "calls"}
    }
    assert ("apex_app_130_authentication_custom_auth", "calls", "HR_AUTH_PKG.AUTHENTICATE") in dependencies
    assert ("apex_app_130_region_summary", "reads_from", "HR_EMP_SUMMARY") in dependencies

    bad_file = tmp_path / "broken.apx"
    bad_file.write_text('page 1 (\n  name: "Broken"\n', encoding="utf-8")
    bad_result = extract_apexlang(bad_file)
    assert "error" in bad_result
    assert bad_result["nodes"] == []


def test_extract_apexlang_resolves_database_mirror(tmp_path: Path):
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


def test_database_mirror_auto_refreshes_on_add_and_edit(tmp_path: Path):
    tables_dir = tmp_path / "database" / "HR" / "tables"
    syn_dir = tmp_path / "database" / "HR" / "synonyms"
    other_tables_dir = tmp_path / "database" / "ARCHIVE" / "tables"
    tables_dir.mkdir(parents=True)
    syn_dir.mkdir(parents=True)
    other_tables_dir.mkdir(parents=True)

    (tables_dir / "HR_WORKERS_OLD.sql").write_text('CREATE TABLE "HR"."HR_WORKERS_OLD" (ID NUMBER);\n', encoding="utf-8")
    (other_tables_dir / "EMP_V2.sql").write_text('CREATE TABLE "ARCHIVE"."EMP_V2" (ID NUMBER);\n', encoding="utf-8")
    syn_file = syn_dir / "HR_WORKERS.sql"
    syn_file.write_text('CREATE SYNONYM "HR"."HR_WORKERS" FOR "HR"."HR_WORKERS_OLD";\n', encoding="utf-8")

    app_dir = tmp_path / "apps" / "HR" / "130" / "pages"
    app_dir.mkdir(parents=True)
    apx_file = app_dir / "p00010.apx"
    apx_file.write_text(SAMPLE_PAGE_APX, encoding="utf-8")
    region_id = "apex_app_130_page_10_region_active_workers"

    # Initial extraction resolves HR_WORKERS through its synonym to HR_WORKERS_OLD.
    first_edges = {(e["source"], e["relation"], e["target"]) for e in extract_apexlang(apx_file)["edges"]}
    assert (region_id, "reads_from", "database_hr_tables_hr_workers_old_hr_hr_workers_old") in first_edges

    # Repoint the synonym (with changed size + explicit mtime bump) without calling clear_cache().
    syn_file.write_text('CREATE SYNONYM "HR"."HR_WORKERS" FOR "ARCHIVE"."EMP_V2";\n  -- updated\n', encoding="utf-8")
    st = syn_file.stat()
    os.utime(syn_file, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))

    second_edges = {(e["source"], e["relation"], e["target"]) for e in extract_apexlang(apx_file)["edges"]}
    assert (region_id, "reads_from", "database_archive_tables_emp_v2_archive_emp_v2") in second_edges

    # Adding a direct table HR_WORKERS in HR takes precedence on the next extraction.
    added_table = tables_dir / "HR_WORKERS.sql"
    added_table.write_text('CREATE TABLE "HR"."HR_WORKERS" (ID NUMBER);\n', encoding="utf-8")

    third_edges = {(e["source"], e["relation"], e["target"]) for e in extract_apexlang(apx_file)["edges"]}
    assert (region_id, "reads_from", "database_hr_tables_hr_workers_hr_hr_workers") in third_edges

    added_table.unlink()
    fourth_edges = {(e["source"], e["relation"], e["target"]) for e in extract_apexlang(apx_file)["edges"]}
    assert (region_id, "reads_from", "database_archive_tables_emp_v2_archive_emp_v2") in fourth_edges


def test_cached_apexlang_extraction_refreshes_when_only_database_mirror_changes(tmp_path):
    app = tmp_path / "apps/HR/130/pages/page.apx"
    app.parent.mkdir(parents=True)
    app.write_text(SAMPLE_PAGE_APX, encoding="utf-8")
    region_id = "apex_app_130_page_10_region_active_workers"

    def reads():
        result = extract([app], root=tmp_path, cache_root=tmp_path, parallel=False)
        return {e["target"] for e in result["edges"]
                if e["source"] == region_id and e["relation"] == "reads_from"}

    unresolved = reads()
    assert any(target.startswith("oracle_ref_hr_workers_") for target in unresolved)
    table = tmp_path / "database/HR/tables/HR_WORKERS.sql"
    table.parent.mkdir(parents=True)
    table.write_text('CREATE TABLE "HR"."HR_WORKERS" (ID NUMBER);\n', encoding="utf-8")
    assert "database_hr_tables_hr_workers_hr_hr_workers" in reads()
    table.unlink()
    assert reads() == unresolved


def test_oracle_mirror_rewire_preserves_unresolved_schema_and_plain_sql_binding(tmp_path):
    pytest.importorskip("tree_sitter_sql")
    sources = {
        "apps/LOCAL/130/pages/page.apx": """\
page 10 (
  region Staff (
    sqlQuery: ```sql
      SELECT * FROM STAFF
    ```
  )
)
""",
        "database/LOCAL/ords/schema.sql": """\
BEGIN
  ORDS.DEFINE_HANDLER(p_pattern => 'unknown', p_source => 'SELECT * FROM STAFF');
  ORDS.DEFINE_HANDLER(p_pattern => 'local', p_source => 'SELECT * FROM LOCAL_DATA');
  ORDS.DEFINE_HANDLER(p_pattern => 'explicit', p_source => 'SELECT * FROM OTHER.NAMED');
END;
/
""",
        "database/LOCAL/tables/LOCAL_DATA.sql": "CREATE TABLE LOCAL_DATA (ID NUMBER);",
        "database/OTHER/tables/STAFF.sql": "CREATE TABLE STAFF (ID NUMBER);",
        "database/OTHER/tables/NAMED.sql": "CREATE TABLE OTHER.NAMED (ID NUMBER);",
        "plain/table.sql": "CREATE TABLE EXAMPLE (ID NUMBER);",
        "plain/view.sql": "CREATE VIEW V_EXAMPLE AS SELECT * FROM EXAMPLE;",
    }
    paths = [tmp_path / name for name in sources]
    for path, sql in zip(paths, sources.values()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(sql, encoding="utf-8")
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    nodes = {n["id"]: n for n in result["nodes"]}
    reads = {
        (nodes[e["source"]]["label"], nodes[e["target"]]["source_file"])
        for e in result["edges"]
        if e["relation"] == "reads_from"
    }
    assert reads == {
        ("Region: Staff", ""),
        ("ORDS GET /unknown", ""),
        ("ORDS GET /local", "database/LOCAL/tables/LOCAL_DATA.sql"),
        ("ORDS GET /explicit", "database/OTHER/tables/NAMED.sql"),
        ("V_EXAMPLE", "plain/table.sql"),
    }


def test_incremental_refresh_only_requeues_apexlang_from_affected_mirrors(tmp_path):
    from graphify.extractors.apexlang import refresh_apexlang_paths

    page = tmp_path / "first/apps/HR/130/pages/page.apx"
    other_page = tmp_path / "second/apps/HR/131/pages/page.apx"
    standalone = tmp_path / "standalone.apx"
    mirror = tmp_path / "first/database/HR/tables/WORKERS.sql"
    synonym = Path("first/database/HR/synonyms/WORKERS.sql")
    plain_sql = tmp_path / "plain.sql"
    corpus = [page, other_page, standalone, mirror, plain_sql]

    assert refresh_apexlang_paths([mirror], corpus, root=tmp_path) == [mirror, page]
    assert refresh_apexlang_paths([], corpus, [synonym], root=tmp_path) == [page]
    assert refresh_apexlang_paths([page, mirror], corpus, root=tmp_path) == [page, mirror]
    assert refresh_apexlang_paths([plain_sql], corpus, root=tmp_path) == [plain_sql]


def test_graph_update_rebinds_unchanged_apexlang_after_mirror_add_and_remove(tmp_path, monkeypatch):
    pytest.importorskip("tree_sitter_sql")
    from graphify.watch import _rebuild_code

    monkeypatch.chdir(tmp_path)
    app = tmp_path / "apps/HR/130/pages/page.apx"
    app.parent.mkdir(parents=True)
    app.write_text(SAMPLE_PAGE_APX, encoding="utf-8")
    table = tmp_path / "database/HR/tables/HR_WORKERS.sql"
    table.parent.mkdir(parents=True)
    graph_path = tmp_path / "graphify-out/graph.json"

    def worker_targets():
        assert _rebuild_code(tmp_path, incremental=True, no_cluster=True)
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in graph["nodes"]}
        return {
            nodes[edge["target"]]["source_file"]
            for edge in graph["links"]
            if edge["relation"] == "reads_from"
            and edge["source"] == "apex_app_130_page_10_region_active_workers"
            and "hr_workers" in edge["target"]
        }

    assert worker_targets() == {""}
    table.write_text('CREATE TABLE "HR"."HR_WORKERS" (ID NUMBER);\n', encoding="utf-8")
    assert worker_targets() == {"database/HR/tables/HR_WORKERS.sql"}
    table.unlink()
    assert worker_targets() == {""}


def test_unresolved_references_are_shared_only_within_their_mirror_and_schema(tmp_path):
    paths = []
    for project, schema, app_id in (
        ("one", "HR", 130), ("one", "HR", 131), ("one", "FIN", 230), ("two", "HR", 330),
    ):
        path = tmp_path / project / f"apps/{schema}/{app_id}/pages/page.apx"
        path.parent.mkdir(parents=True)
        path.write_text("page 10 (\n  region Staff (\n    tableName: STAFF\n  )\n)\n")
        paths.append(path)
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    graph = build([result], root=tmp_path)
    targets = {
        e["source"]: e["target"] for e in result["edges"] if e["relation"] == "reads_from"
    }
    assert set(targets) == {
        f"apex_app_{app_id}_page_10_region_staff" for app_id in (130, 131, 230, 330)
    }
    assert targets["apex_app_130_page_10_region_staff"] == targets["apex_app_131_page_10_region_staff"]
    assert len(set(targets.values())) == 3
    assert all(graph.nodes[target]["label"] == "STAFF" for target in targets.values())


def test_unicode_from_clause_consumes_quoted_identifiers_and_bare_names():
    command = """
from graphify.extractors.apexlang import _sql_dependencies
reads, writes, calls = _sql_dependencies(
    'SELECT * FROM "Équipe, FROM (detail)" e, موظف WHERE e.id = 1'
)
assert reads == {"ÉQUIPE, FROM (DETAIL)", "موظف"}, reads
assert writes == calls == set()
"""
    result = subprocess.run(
        [sys.executable, "-c", command], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=5,
    )
    assert result.returncode == 0, result.stderr


def test_navigation_application_is_scoped_to_its_property_block(tmp_path):
    app = tmp_path / "apps/HR/130/pages/page.apx"
    app.parent.mkdir(parents=True)
    app.write_text("""\
page 10 (
  dynamicAction Navigate (
    link {
      target: {
        page: 20
        application: 900
      }
      fallback: {
        page: 21
      }
    }
    name: "Documentation says page: 99"
    target: { page: 23 application: 902 clearCache: "text page: 98" }
    link: "f?p=901:22:"
  )
)
""")
    result = extract_apexlang(app)
    targets = {e["target"] for e in result["edges"] if e["relation"] == "navigates_to"}
    assert targets == {
        "apex_app_900_page_20", "apex_app_130_page_21",
        "apex_app_901_page_22", "apex_app_902_page_23",
    }
