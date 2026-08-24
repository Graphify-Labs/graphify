"""SQL parsing is a core capability, not an optional extra.

tree-sitter-sql used to live behind the [sql] extra, so a default
`uv tool install graphifyy` / `pipx install graphifyy` silently skipped every
.sql file in the corpus: the extractor bailed with an error, the #1745 warning
was the only signal, and until #2543 the failure was even stamped into the
incremental manifest. These tests pin the fix at the packaging layer so a
regression (the dependency sliding back into an extra) fails the suite rather
than resurfacing as a field report.
"""
from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from graphify import extract as extractmod
from graphify.extract import extract

REPO_ROOT = Path(__file__).resolve().parent.parent


def _pyproject() -> dict:
    with open(REPO_ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


def test_tree_sitter_sql_is_a_core_dependency():
    """The grammar must be in [project.dependencies], not only in an extra."""
    deps = _pyproject()["project"]["dependencies"]
    sql_deps = [d for d in deps if d.replace("_", "-").startswith("tree-sitter-sql")]
    assert sql_deps, (
        "tree-sitter-sql is missing from [project.dependencies]; a default "
        "install would silently skip every .sql file again (#1745)"
    )


def test_tree_sitter_sql_core_pin_stays_inside_supported_tree_sitter_range():
    """The core pin must carry an upper bound like every other grammar pin."""
    deps = _pyproject()["project"]["dependencies"]
    (pin,) = [d for d in deps if d.replace("_", "-").startswith("tree-sitter-sql")]
    assert "<" in pin, f"tree-sitter-sql core pin has no upper bound: {pin!r}"


def test_sql_extension_is_not_mapped_to_an_optional_extra():
    """#1745's hint map must not send users to a now-redundant [sql] extra."""
    assert ".sql" not in extractmod._EXTRA_FOR_EXTENSION, (
        "_EXTRA_FOR_EXTENSION still maps .sql to an extra; the 'install "
        "graphifyy[sql]' hint is wrong now that the grammar is core"
    )


def test_tree_sitter_sql_imports_in_this_environment():
    """The dev environment itself must satisfy the core dependency."""
    import tree_sitter_sql  # noqa: F401


def test_sql_corpus_produces_structural_nodes_and_edges(tmp_path):
    """Regression: a table/view/procedure corpus yields real structure.

    Guards the end-to-end path (dispatch -> tree-sitter parse -> node/edge
    emission), not just the packaging declaration: representative DDL must
    produce object nodes, `contains` edges from the file, a foreign-key
    `references` edge, and `reads_from` edges from the view and procedure.
    """
    schema = tmp_path / "schema.sql"
    schema.write_text(
        "CREATE TABLE organizations (\n"
        "  id INT PRIMARY KEY,\n"
        "  name TEXT NOT NULL\n"
        ");\n"
        "CREATE TABLE users (\n"
        "  id INT PRIMARY KEY,\n"
        "  org_id INT REFERENCES organizations(id)\n"
        ");\n"
        "CREATE VIEW active_users AS\n"
        "  SELECT * FROM users WHERE active = 1;\n"
        "CREATE PROCEDURE prune_users()\n"
        "BEGIN\n"
        "  DELETE FROM users WHERE id IN (SELECT id FROM active_users);\n"
        "END;\n"
    )

    r = extract([schema], cache_root=tmp_path)
    labels = {n["label"] for n in r["nodes"]}
    assert {"organizations", "users", "active_users"} <= labels, labels
    assert any(label.startswith("prune_users") for label in labels), labels

    relations = {e["relation"] for e in r["edges"]}
    assert "contains" in relations, "file node must contain the SQL objects"
    assert "references" in relations, "users.org_id FK must emit a references edge"
    assert "reads_from" in relations, "view/procedure bodies must emit reads_from edges"

    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"dangling edge source: {e['source']}"
