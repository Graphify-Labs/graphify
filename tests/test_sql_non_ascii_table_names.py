"""#5250: a table named with non-ASCII letters must not yield an empty-id node."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_sql")

from graphify.extractors.sql import extract_sql  # noqa: E402

# The grammar's identifier rule is ASCII-only, so it keeps just the `_` of
# `заказы_клиентов`; that used to mint a node with id "" and an edge to it.
STATEMENTS = [
    "INSERT INTO заказы_клиентов(a) VALUES (1);",
    "DELETE FROM заказы_клиентов WHERE a = 1;",
    "UPDATE заказы_клиентов z SET z.x = 'x';",
    "SELECT 1 FROM заказы_клиентов g;",
]


@pytest.mark.parametrize("stmt", STATEMENTS)
def test_no_empty_id_node_or_edge(tmp_path: Path, stmt: str) -> None:
    path = tmp_path / "cyr.sql"
    path.write_text(f"CREATE OR REPLACE PROCEDURE p IS\nBEGIN\n  {stmt}\nEND;\n/\n", encoding="utf-8")
    result = extract_sql(path)
    assert all(n["id"] for n in result["nodes"])
    assert all(e["source"] and e["target"] for e in result["edges"])
