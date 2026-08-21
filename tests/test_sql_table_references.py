"""SQL tables are linked to the application code that queries them (#2884).

Before this pass a table declared in `db/schema.sql` had no edge to the `.ts`
file whose query reads `SELECT … FROM that_table` — the whole data layer landed
as degree-1 orphans and the graph could not answer "what breaks if I change this
table?".
"""
from __future__ import annotations

import pytest

from graphify.extract import extract

pytest.importorskip("tree_sitter_sql")
pytest.importorskip("tree_sitter_typescript")


def _corpus(tmp_path):
    db = tmp_path / "db"
    db.mkdir()
    (db / "schema.sql").write_text(
        "CREATE TABLE volunteer_assignments (id INT, note TEXT);\n"
        "CREATE TABLE events (id INT);\n"
        "CREATE TABLE never_queried (id INT);\n"
    )
    migrations = db / "migrations"
    migrations.mkdir()
    (migrations / "035_volunteers.sql").write_text(
        "CREATE TABLE volunteer_assignments (id INT, note TEXT);\n"
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "assignments.ts").write_text(
        "export async function load(id: number) {\n"
        "  return await query(`\n"
        "    SELECT a.id, a.note\n"
        "    FROM volunteer_assignments\n"
        "    WHERE a.id = ?`, [id]);\n"
        "}\n"
    )
    (src / "roster.ts").write_text(
        "export async function add(v: string) {\n"
        "  await query(`INSERT INTO volunteer_assignments (note) VALUES (?)`, [v]);\n"
        "}\n"
    )
    return tmp_path, db, src


def _refs(result):
    """(source_file basename, target label) for every sql_table reference edge."""
    labels = {n["id"]: n.get("label") for n in result["nodes"]}
    out = []
    for e in result["edges"]:
        if e.get("context") != "sql_table":
            continue
        out.append((str(e.get("source_file", "")).replace("\\", "/").split("/")[-1],
                    labels.get(e["target"])))
    return sorted(out)


def test_queried_table_links_to_every_declaration_site(tmp_path):
    root, db, src = _corpus(tmp_path)
    paths = sorted(db.rglob("*.sql")) + sorted(src.glob("*.ts"))
    result = extract(paths, cache_root=tmp_path)

    refs = _refs(result)
    # Both querying files link to the table, and each links to BOTH declaration
    # sites (schema.sql and the migration that created it), so tracing a table
    # also reaches its migration history.
    assert refs.count(("assignments.ts", "volunteer_assignments")) == 2
    assert refs.count(("roster.ts", "volunteer_assignments")) == 2

    # Edges are EXTRACTED with full confidence: the name is written verbatim in
    # a SQL keyword position, which is a checkable claim rather than a guess.
    sql_edges = [e for e in result["edges"] if e.get("context") == "sql_table"]
    assert all(e["confidence"] == "EXTRACTED" for e in sql_edges)
    assert all(e["confidence_score"] == 1.0 for e in sql_edges)
    assert all(e["relation"] == "references" for e in sql_edges)


def test_table_is_no_longer_a_degree_one_orphan(tmp_path):
    root, db, src = _corpus(tmp_path)
    paths = sorted(db.rglob("*.sql")) + sorted(src.glob("*.ts"))
    result = extract(paths, cache_root=tmp_path)

    table_ids = {
        n["id"] for n in result["nodes"]
        if n.get("label") == "volunteer_assignments"
    }
    degree = sum(
        1 for e in result["edges"]
        if e.get("source") in table_ids or e.get("target") in table_ids
    )
    assert degree > 2, "the table should reach the routes that query it"


def test_a_table_named_like_a_variable_is_not_falsely_linked(tmp_path):
    """The precision trap the issue warns about.

    Matching a table name on a word boundary and applying the SQL-context test
    file-wide — "does this file contain SQL anywhere, and does this name appear
    anywhere in it" — produced 130 phantom `events` edges that were all
    JavaScript variables named `events`. The table must sit in a SQL keyword
    position IN THE SAME MATCH.
    """
    root, db, src = _corpus(tmp_path)
    (src / "widget.ts").write_text(
        "const events = [1, 2, 3];\n"
        "export function count() {\n"
        "  return events.length + events.filter(Boolean).length;\n"
        "}\n"
        "// note: we also SELECT things from the events array below\n"
        "export const first = events[0];\n"
    )
    paths = sorted(db.rglob("*.sql")) + sorted(src.glob("*.ts"))
    result = extract(paths, cache_root=tmp_path)

    assert ("widget.ts", "events") not in _refs(result)
    # ...while the genuine references are still found.
    assert ("assignments.ts", "volunteer_assignments") in _refs(result)


def test_comments_and_prose_are_not_queries(tmp_path):
    """#2884 review: the same phantom class one level up from a bare identifier.

    A table name after a SQL keyword is not a query when it sits in a comment or
    in ordinary prose, and all three of these minted a `references` edge while
    the matcher scanned raw file bytes.
    """
    root, db, src = _corpus(tmp_path)
    (src / "comment.ts").write_text(
        "// SELECT foo FROM events\n"
        "export const n = 1;\n"
    )
    (src / "prose.ts").write_text(
        'const s = "the FROM events keyword";\n'
        "export const t = s;\n"
    )
    (src / "docs.py").write_text(
        '"""Docs: you can JOIN events with assets here."""\n'
        "N = 1\n"
    )
    paths = (sorted(db.rglob("*.sql")) + sorted(src.glob("*.ts"))
             + sorted(src.glob("*.py")))
    result = extract(paths, cache_root=tmp_path)

    refs = _refs(result)
    assert ("comment.ts", "events") not in refs
    assert ("prose.ts", "events") not in refs
    assert ("docs.py", "events") not in refs
    assert ("assignments.ts", "volunteer_assignments") in refs


def test_schema_qualified_table_links_both_reference_forms(tmp_path):
    """#2884 review: labels are stored verbatim, so a Postgres/T-SQL corpus
    declares `public.users` — and matching on the label alone gave it zero
    edges, whichever way the query spells the reference."""
    db = tmp_path / "db"
    db.mkdir()
    (db / "schema.sql").write_text("CREATE TABLE public.users (id INT);\n")
    src = tmp_path / "src"
    src.mkdir()
    (src / "bare.ts").write_text("q(`SELECT id FROM users`);\n")
    (src / "qualified.ts").write_text("q(`SELECT id FROM public.users`);\n")

    paths = sorted(db.glob("*.sql")) + sorted(src.glob("*.ts"))
    result = extract(paths, cache_root=tmp_path)
    assert {f for f, label in _refs(result)} == {"bare.ts", "qualified.ts"}


def test_unreferenced_table_gets_no_edges(tmp_path):
    """A useful side effect: tables with no SQL-position reference anywhere are
    surfaced as dead schema rather than papered over."""
    root, db, src = _corpus(tmp_path)
    paths = sorted(db.rglob("*.sql")) + sorted(src.glob("*.ts"))
    result = extract(paths, cache_root=tmp_path)
    assert not any(label == "never_queried" for _, label in _refs(result))


def test_opt_out_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_NO_SQL_LINKS", "1")
    root, db, src = _corpus(tmp_path)
    paths = sorted(db.rglob("*.sql")) + sorted(src.glob("*.ts"))
    result = extract(paths, cache_root=tmp_path)
    assert _refs(result) == []


def test_quoted_table_names_match(tmp_path):
    """MySQL backticks, standard double quotes, T-SQL brackets (cf. #2712)."""
    db = tmp_path / "db"
    db.mkdir()
    (db / "schema.sql").write_text("CREATE TABLE user_email_preferences (id INT);\n")
    src = tmp_path / "src"
    src.mkdir()
    (src / "mysql.ts").write_text('q("SELECT * FROM `user_email_preferences`");\n')
    (src / "pg.ts").write_text('q(`SELECT * FROM "user_email_preferences"`);\n')
    (src / "tsql.ts").write_text("q(`SELECT * FROM [user_email_preferences]`);\n")

    paths = sorted(db.glob("*.sql")) + sorted(src.glob("*.ts"))
    result = extract(paths, cache_root=tmp_path)
    linked = {f for f, label in _refs(result) if label == "user_email_preferences"}
    assert linked == {"mysql.ts", "pg.ts", "tsql.ts"}


def _run_cli(monkeypatch, argv):
    import graphify.__main__ as mainmod
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", argv)
    try:
        mainmod.main()
    except SystemExit as exc:
        return exc.code or 0
    return 0


def _graph_edges(out_dir):
    import json
    return json.loads((out_dir / "graphify-out" / "graph.json").read_text())


def test_cli_flag_skips_the_pass(tmp_path, monkeypatch):
    """#2884 review: the pass is on by default, so the opt-out has to be a real
    flag and not only an env var a user has to know exists."""
    monkeypatch.delenv("GRAPHIFY_NO_SQL_LINKS", raising=False)
    root, db, src = _corpus(tmp_path)
    out = tmp_path / "out"
    assert _run_cli(monkeypatch, [
        "graphify", "extract", str(root), "--code-only", "--no-cluster",
        "--no-sql-links", "--out", str(out),
    ]) == 0
    graph = _graph_edges(out)
    links = [e for e in graph.get("links", graph.get("edges", []))
             if e.get("context") == "sql_table"]
    assert links == []


def test_cli_emits_the_links_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("GRAPHIFY_NO_SQL_LINKS", raising=False)
    root, db, src = _corpus(tmp_path)
    out = tmp_path / "out"
    assert _run_cli(monkeypatch, [
        "graphify", "extract", str(root), "--code-only", "--no-cluster",
        "--out", str(out),
    ]) == 0
    graph = _graph_edges(out)
    links = [e for e in graph.get("links", graph.get("edges", []))
             if e.get("context") == "sql_table"]
    assert links, "the pass is on by default — that is the point of the issue"
