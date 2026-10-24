"""#4635: T-SQL bracket names, stored-procedure reads, and writes."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_sql")

from graphify.extract import extract, extract_sql  # noqa: E402

READ = "reads_from"
STRUCTURAL = {"contains"}

ISSUE_FILES = {
    "Db/Views/Country.sql":
        "CREATE VIEW [dbo].[Country] AS SELECT CN_KEY AS Id, CN_NAME AS Name FROM [dbo].[tbl_Country]\nGO\n",
    "Db/Procs/AddPayment.sql":
        "CREATE PROCEDURE [dbo].[AddPayment] @orderId INT, @sum MONEY\n"
        "AS\n"
        "BEGIN\n"
        "    DECLARE @total MONEY\n"
        "    SELECT @total = o.Total FROM [dbo].[Orders] o WHERE o.Id = @orderId\n"
        "    INSERT INTO [dbo].[Payments] (OrderId, Amount) VALUES (@orderId, @sum)\n"
        "    UPDATE [dbo].[Orders] SET Paid = Paid + @sum WHERE Id = @orderId\n"
        "END\nGO\n",
    "Db/Procs/GetOrderTotal.sql":
        "CREATE PROCEDURE [dbo].[GetOrderTotal] @orderId INT\n"
        "AS\n"
        "SELECT o.Total FROM [dbo].[Orders] o JOIN [dbo].[Payments] p ON p.OrderId = o.Id WHERE o.Id = @orderId\n"
        "GO\n",
    "Db/Procs/GetOrderTotalPlain.sql":
        "CREATE PROCEDURE dbo.GetOrderTotalPlain @orderId INT\n"
        "AS\n"
        "SELECT o.Total FROM dbo.Orders o JOIN dbo.Payments p ON p.OrderId = o.Id WHERE o.Id = @orderId\n"
        "GO\n",
}


def _write(tmp_path: Path, files: dict[str, str]) -> list[Path]:
    paths = []
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        paths.append(p)
    return paths


def _name(label: str) -> str:
    """Compare names without delimiters, call parens or case."""
    return label.replace("[", "").replace("]", "").replace('"', "").removesuffix("()").lower()


def _triples(result: dict) -> set[tuple[str, str, str]]:
    label = {n["id"]: n["label"] for n in result["nodes"]}
    return {
        (_name(label.get(e["source"], e["source"])), e["relation"], _name(label.get(e["target"], e["target"])))
        for e in result["edges"]
        if e["relation"] not in STRUCTURAL
    }


def _extract_project(tmp_path: Path, files: dict[str, str]) -> dict:
    return extract(_write(tmp_path, files), root=tmp_path)


# T1 -- one table written two ways in one file is one node
@pytest.mark.parametrize("table, ref", [
    ("[dbo].[Orders]", "dbo.Orders"),
    ("dbo.Orders", "[dbo].[Orders]"),
    ("[dbo].[Orders]", "[dbo].[Orders]"),
])
def test_bracketed_and_plain_names_resolve_to_the_defined_table(tmp_path, table, ref):
    p = tmp_path / "schema.sql"
    p.write_text(f"CREATE TABLE {table} (Id INT);\nCREATE VIEW dbo.V AS SELECT Id FROM {ref};\n")
    r = extract_sql(p)
    table_ids = [n["id"] for n in r["nodes"] if n.get("source_file") and _name(n["label"]) == "dbo.orders"]
    assert len(table_ids) == 1, [n["label"] for n in r["nodes"]]
    reads = [e for e in r["edges"] if e["relation"] == READ]
    assert [e["target"] for e in reads] == table_ids, reads


# T2 -- no label keeps a half-stripped bracket
def test_issue_repro_labels_have_no_half_stripped_brackets(tmp_path):
    r = _extract_project(tmp_path, ISSUE_FILES)
    bad = [n["label"] for n in r["nodes"] if "].[" in n["label"] or n["label"].startswith("dbo]")]
    assert not bad, bad


# T3 -- each procedure in the issue reads its tables
@pytest.mark.parametrize("proc, table", [
    ("dbo.getordertotal", "dbo.orders"),
    ("dbo.getordertotal", "dbo.payments"),
    ("dbo.getordertotalplain", "dbo.orders"),
    ("dbo.getordertotalplain", "dbo.payments"),
    ("dbo.addpayment", "dbo.orders"),
])
def test_issue_repro_procedure_reads_its_tables(tmp_path, proc, table):
    calls = _triples(_extract_project(tmp_path, ISSUE_FILES))
    assert (proc, READ, table) in calls, sorted(calls)


def test_issue_repro_view_still_reads_its_table(tmp_path):
    calls = _triples(_extract_project(tmp_path, ISSUE_FILES))
    assert ("dbo.country", READ, "dbo.tbl_country") in calls, sorted(calls)


# T4 -- not T-SQL only: any CREATE PROCEDURE body, any dialect
@pytest.mark.parametrize("src", [
    "CREATE PROCEDURE p AS SELECT a FROM t1 JOIN t2 ON t1.id = t2.id;\n",
    "CREATE PROCEDURE p(x INT) AS SELECT a FROM t1 JOIN t2 ON t1.id = t2.id;\n",
    "CREATE PROC p @x INT AS BEGIN SELECT a FROM t1 JOIN t2 ON t1.id = t2.id END\n",
])
def test_plain_procedure_reads_its_tables(tmp_path, src):
    p = tmp_path / "p.sql"
    p.write_text(src)
    calls = _triples(extract_sql(p))
    assert ("p", READ, "t1") in calls and ("p", READ, "t2") in calls, sorted(calls)


# T5 -- writes make an edge, and it is not a read. The relation name is not decided here.
@pytest.mark.parametrize("stmt, table", [
    ("INSERT INTO dbo.Payments (OrderId) VALUES (@id)", "dbo.payments"),
    ("UPDATE dbo.Payments SET Amount = 0 WHERE OrderId = @id", "dbo.payments"),
    ("DELETE FROM dbo.Payments WHERE OrderId = @id", "dbo.payments"),
    ("MERGE INTO dbo.Payments AS t USING dbo.Staging AS s ON t.OrderId = s.OrderId "
     "WHEN MATCHED THEN DELETE;", "dbo.payments"),
])
def test_procedure_write_makes_a_non_read_edge(tmp_path, stmt, table):
    p = tmp_path / "w.sql"
    p.write_text(f"CREATE PROCEDURE dbo.W @id INT AS\nBEGIN\n    {stmt}\nEND\nGO\n")
    r = extract_sql(p)
    calls = _triples(r)
    writes = {rel for s, rel, t in calls if s == "dbo.w" and t == table and rel != READ}
    assert writes, sorted(calls)


def test_issue_repro_addpayment_writes_payments_and_orders(tmp_path):
    calls = _triples(_extract_project(tmp_path, ISSUE_FILES))
    for table in ("dbo.payments", "dbo.orders"):
        assert any(s == "dbo.addpayment" and t == table and rel != READ for s, rel, t in calls), sorted(calls)
    # Payments is only written in AddPayment, never read.
    assert ("dbo.addpayment", READ, "dbo.payments") not in calls, sorted(calls)


# T8 -- guards: things that are not tables never become targets
def test_issue_repro_variables_aliases_and_columns_are_not_tables(tmp_path):
    r = _extract_project(tmp_path, ISSUE_FILES)
    targets = {t for _s, _rel, t in _triples(r)}
    for not_a_table in ("o", "p", "@total", "total", "paid", "orderid", "amount", "id", "go"):
        assert not_a_table not in targets, sorted(targets)


def test_cte_inside_a_procedure_is_not_a_table(tmp_path):
    p = tmp_path / "c.sql"
    p.write_text("CREATE PROCEDURE dbo.C AS\nBEGIN\n"
                 "    WITH recent AS (SELECT Id FROM dbo.Orders)\n"
                 "    SELECT Id FROM recent\nEND\nGO\n")
    calls = _triples(extract_sql(p))
    assert not any(t == "recent" for _s, _rel, t in calls), sorted(calls)


def test_two_procedures_in_one_file_keep_their_own_tables(tmp_path):
    p = tmp_path / "two.sql"
    p.write_text("CREATE PROCEDURE dbo.A AS SELECT x FROM dbo.T1;\n"
                 "CREATE PROCEDURE dbo.B AS SELECT y FROM dbo.T2;\n")
    calls = _triples(extract_sql(p))
    assert ("dbo.a", READ, "dbo.t2") not in calls, sorted(calls)
    assert ("dbo.b", READ, "dbo.t1") not in calls, sorted(calls)


def test_top_level_statements_outside_a_routine_get_no_owner(tmp_path):
    p = tmp_path / "script.sql"
    p.write_text("SELECT a FROM dbo.T1;\nINSERT INTO dbo.T2 (a) VALUES (1);\n")
    calls = _triples(extract_sql(p))
    assert not calls, sorted(calls)


def test_function_and_view_reads_are_unchanged(tmp_path):
    p = tmp_path / "f.sql"
    p.write_text("CREATE FUNCTION f() RETURNS int AS $$ SELECT a FROM t1 $$ LANGUAGE sql;\n"
                 "CREATE VIEW v AS SELECT a FROM t2;\n")
    calls = _triples(extract_sql(p))
    assert ("f", READ, "t1") in calls and ("v", READ, "t2") in calls, sorted(calls)


WRITE = "writes_to"


def _raw_labels(result: dict) -> set[str]:
    return {n["label"] for n in result["nodes"]}


# T2b -- the label policy: brackets stripped, schema kept
def test_issue_repro_labels_are_bracket_free(tmp_path):
    labels = _raw_labels(_extract_project(tmp_path, ISSUE_FILES))
    for want in ("dbo.Country", "dbo.tbl_Country", "dbo.AddPayment()", "dbo.GetOrderTotal()",
                 "dbo.GetOrderTotalPlain()", "dbo.Orders", "dbo.Payments"):
        assert want in labels, sorted(labels)


def test_escaped_bracket_and_double_quoted_labels(tmp_path):
    p = tmp_path / "q.sql"
    p.write_text('CREATE VIEW "dbo"."V" AS SELECT a FROM "dbo"."T";\n'
                 "CREATE PROCEDURE [dbo].[a]]b] AS SELECT x FROM dbo.T1\nGO\n")
    labels = _raw_labels(extract_sql(p))
    assert '"dbo"."V"' in labels, sorted(labels)
    assert "dbo.a]b()" in labels, sorted(labels)


# T5b -- the write relation is writes_to
def test_issue_repro_addpayment_write_relation(tmp_path):
    calls = _triples(_extract_project(tmp_path, ISSUE_FILES))
    assert ("dbo.addpayment", WRITE, "dbo.payments") in calls, sorted(calls)
    assert ("dbo.addpayment", WRITE, "dbo.orders") in calls, sorted(calls)


def test_delete_from_is_a_write_not_a_read(tmp_path):
    p = tmp_path / "d.sql"
    p.write_text("CREATE PROCEDURE dbo.D AS\nBEGIN\n    DELETE FROM dbo.Payments WHERE Amount = 0\nEND\nGO\n")
    calls = _triples(extract_sql(p))
    assert ("dbo.d", WRITE, "dbo.payments") in calls, sorted(calls)
    assert ("dbo.d", READ, "dbo.payments") not in calls, sorted(calls)


def test_select_into_writes_the_target_and_reads_the_source(tmp_path):
    p = tmp_path / "si.sql"
    p.write_text("CREATE PROCEDURE dbo.S AS\nBEGIN\n"
                 "    SELECT Id INTO dbo.Archive FROM dbo.Orders WHERE Paid = Total\nEND\nGO\n")
    calls = _triples(extract_sql(p))
    assert ("dbo.s", WRITE, "dbo.archive") in calls, sorted(calls)
    assert ("dbo.s", READ, "dbo.orders") in calls, sorted(calls)


# T9 -- alias updates resolve to the aliased table
def test_update_through_an_alias_writes_the_aliased_table(tmp_path):
    p = tmp_path / "a.sql"
    p.write_text("CREATE PROCEDURE dbo.U AS\nBEGIN\n"
                 "    UPDATE o SET Paid = 1 FROM [dbo].[Orders] o JOIN dbo.Payments p ON p.OrderId = o.Id\n"
                 "END\nGO\n")
    calls = _triples(extract_sql(p))
    assert ("dbo.u", WRITE, "dbo.orders") in calls, sorted(calls)
    assert not any(t in ("o", "p") for _s, _rel, t in calls), sorted(calls)


# T10 -- temp tables and table variables are not schema objects
def test_temp_tables_and_table_variables_are_skipped(tmp_path):
    p = tmp_path / "t.sql"
    p.write_text("CREATE PROCEDURE dbo.T AS\nBEGIN\n"
                 "    DECLARE @ids TABLE (Id INT)\n"
                 "    SELECT Id INTO #work FROM dbo.Orders\n"
                 "    INSERT INTO @ids (Id) SELECT Id FROM #work\n"
                 "    INSERT INTO ##shared (Id) SELECT Id FROM @ids\n"
                 "END\nGO\n")
    calls = _triples(extract_sql(p))
    assert ("dbo.t", READ, "dbo.orders") in calls, sorted(calls)
    assert not any(t.startswith(("#", "@")) or t in ("work", "shared", "ids") for _s, _rel, t in calls), sorted(calls)


# T11 -- body boundaries, comments and strings
def test_go_separated_procedures_keep_their_own_tables(tmp_path):
    p = tmp_path / "go.sql"
    p.write_text("CREATE PROCEDURE dbo.A AS\nSELECT x FROM dbo.T1\nGO\n"
                 "CREATE PROCEDURE dbo.B AS\nSELECT y FROM dbo.T2\nGO\n")
    calls = _triples(extract_sql(p))
    assert ("dbo.a", READ, "dbo.t1") in calls and ("dbo.b", READ, "dbo.t2") in calls, sorted(calls)
    assert ("dbo.a", READ, "dbo.t2") not in calls and ("dbo.b", READ, "dbo.t1") not in calls, sorted(calls)


def test_tables_in_comments_and_strings_are_not_read(tmp_path):
    p = tmp_path / "cs.sql"
    p.write_text("CREATE PROCEDURE dbo.C AS\nBEGIN\n"
                 "    -- SELECT 1 FROM dbo.Fake1\n"
                 "    /* UPDATE dbo.Fake2 SET a = 1 */\n"
                 "    EXEC('DELETE FROM dbo.Fake3')\n"
                 "    SELECT a FROM dbo.Real\nEND\nGO\n")
    calls = _triples(extract_sql(p))
    assert ("dbo.c", READ, "dbo.real") in calls, sorted(calls)
    assert not any(t.startswith("dbo.fake") for _s, _rel, t in calls), sorted(calls)


def test_one_edge_per_routine_relation_and_table(tmp_path):
    r = _extract_project(tmp_path, ISSUE_FILES)
    label = {n["id"]: n["label"] for n in r["nodes"]}
    keys = [(label[e["source"]], e["relation"], label[e["target"]])
            for e in r["edges"] if e["relation"] in (READ, WRITE)]
    assert len(keys) == len(set(keys)), sorted(keys)
