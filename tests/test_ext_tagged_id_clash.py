"""#4449: a symbol must not take a same-stem sibling's file id.

``extract()`` renames every file's OLD file-level id (its path WITH the extension,
``esquema_x_sql`` for ``esquema/x.sql``) to the canonical one (``esquema_x``). A symbol of
another file can spell the same string: ``const sql`` in ``x.mjs`` is minted
``{stem}_{name}`` = ``esquema_x_sql``. The rename used to hit it too, so the symbol took
the file node's id, was salted next to it, and dedup kept one of the two: the file node
of ``x.mjs`` ended up labelled ``sql`` and ``graphify explain "x.mjs"`` found nothing.
Edges and calls that named the symbol followed the wrong rename.

These tests pin the cause (a key is renamed only for the file that minted it, wherever
another file's own symbol spells it) and the controls that must not move.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.build import build
from graphify.extract import extract, extract_js

ISSUE_MJS = (
    'import postgres from "postgres";\n'
    "const sql = postgres(process.env.U);\n"
    "async function prueba(){ return sql`select 1` }\n"
)
SQL = "create table t(a int);\n"


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _run(root: Path, files: dict[str, str], monkeypatch, *, absolute: bool = False) -> dict:
    """Write ``files`` under ``root`` and run extract() on them, relative or absolute."""
    for rel, text in files.items():
        _write(root, rel, text)
    if absolute:
        return extract([root / rel for rel in files], root=root, cache_root=root / "c")
    monkeypatch.chdir(root)
    return extract([Path(rel) for rel in files], root=Path("."), cache_root=root / "c")


def _node(result: dict, label: str, source_file: str) -> dict:
    found = [n for n in result["nodes"] if n.get("label") == label and n.get("source_file") == source_file]
    assert len(found) == 1, f"expected one node {label!r} from {source_file}; got {found}"
    return found[0]


def _edges(result: dict, relation: str) -> list[tuple[str, str]]:
    return [(e["source"], e["target"]) for e in result["edges"] if e.get("relation") == relation]


def _assert_unique_ids(result: dict) -> None:
    ids = [n["id"] for n in result["nodes"]]
    assert len(ids) == len(set(ids)), f"an id is used by two nodes: {sorted(i for i in ids if ids.count(i) > 1)}"


@pytest.mark.parametrize("absolute", [False, True], ids=["relative", "absolute"])
def test_variable_named_like_the_sibling_extension_keeps_its_own_node(tmp_path, monkeypatch, absolute):
    """The issue: x.mjs with ``const sql`` next to x.sql. Both nodes survive, apart."""
    result = _run(tmp_path, {"esquema/x.mjs": ISSUE_MJS, "esquema/x.sql": SQL}, monkeypatch, absolute=absolute)

    file_node = _node(result, "x.mjs", "esquema/x.mjs")
    variable = _node(result, "sql", "esquema/x.mjs")
    sql_file = _node(result, "x.sql", "esquema/x.sql")
    assert len({file_node["id"], variable["id"], sql_file["id"]}) == 3
    _assert_unique_ids(result)


def test_the_file_node_is_still_found_by_label_after_build(tmp_path, monkeypatch):
    """What ``graphify explain "x.mjs"`` needs: build() must not drop the file node."""
    result = _run(tmp_path, {"esquema/x.mjs": ISSUE_MJS, "esquema/x.sql": SQL}, monkeypatch)
    labels = {d.get("label") for _, d in build([result]).nodes(data=True)}
    assert {"x.mjs", "sql", "x.sql"} <= labels


def test_edges_follow_the_right_node_when_x_mjs_also_imports_x_sql(tmp_path, monkeypatch):
    """One id string, three meanings: the import (stamped with target_file) ends on the
    x.sql FILE node; ``contains`` and ``calls`` end on the ``sql`` VARIABLE; no self-loop."""
    mjs = 'import raw from "./x.sql";\n' + ISSUE_MJS
    result = _run(tmp_path, {"esquema/x.mjs": mjs, "esquema/x.sql": SQL}, monkeypatch)
    file_node = _node(result, "x.mjs", "esquema/x.mjs")["id"]
    variable = _node(result, "sql", "esquema/x.mjs")["id"]
    sql_file = _node(result, "x.sql", "esquema/x.sql")["id"]
    prueba = _node(result, "prueba()", "esquema/x.mjs")["id"]

    assert (file_node, sql_file) in _edges(result, "imports_from")
    assert (file_node, variable) in _edges(result, "contains")
    assert (prueba, variable) in _edges(result, "calls")
    assert not [e for e in result["edges"] if e["source"] == e["target"]]


def test_a_sibling_without_nodes_still_keeps_the_variable_apart(tmp_path, monkeypatch):
    """x.ts + x.css: x.css yields no nodes, so nothing is salted. ``css`` still must not
    take x.ts's file id. (collect_files skips .css; a Python caller passes it explicitly.)"""
    ts = "function makeCss(){ return 1 }\nexport const css = makeCss();\nexport function g(){ return css }\n"
    result = _run(tmp_path, {"web/x.ts": ts, "web/x.css": "a { color: red }\n"}, monkeypatch)
    assert _node(result, "x.ts", "web/x.ts")["id"] != _node(result, "css", "web/x.ts")["id"]
    _assert_unique_ids(result)


def test_a_variable_keeps_the_id_the_extractor_gave_it_next_to_a_js_map(tmp_path, monkeypatch):
    """x.js + x.js.map: ``js_map`` was renamed to x.js.map's file id (a node that does not exist)."""
    js = "function mk(){ return 1 }\nconst js_map = mk();\nfunction g(){ return js_map }\n"
    result = _run(tmp_path, {"web/x.js": js, "web/x.js.map": '{"version":3}\n'}, monkeypatch)
    minted = {n["label"]: n["id"] for n in extract_js(Path("web/x.js"))["nodes"]}
    assert _node(result, "js_map", "web/x.js")["id"] == minted["js_map"]


def test_a_python_function_named_like_the_sibling_extension_keeps_its_calls(tmp_path, monkeypatch):
    """def sql() in x.py next to x.sql: the function survives and its call edge starts at it,
    not at the file node (a caller id that followed the file-level rename)."""
    files = {
        "pyfn/__init__.py": "",
        "pyfn/util.py": "def helper():\n    return 1\n",
        "pyfn/x.py": "from pyfn.util import helper\n\n\ndef sql():\n    return helper()\n",
        "pyfn/x.sql": SQL,
    }
    result = _run(tmp_path, files, monkeypatch)
    function = _node(result, "sql()", "pyfn/x.py")["id"]
    file_node = _node(result, "x.py", "pyfn/x.py")["id"]
    helper = _node(result, "helper()", "pyfn/util.py")["id"]
    assert function != file_node
    assert (function, helper) in _edges(result, "calls")
    assert (file_node, function) in _edges(result, "contains")
    _assert_unique_ids(result)


def test_an_unstamped_import_on_a_contested_key_ends_where_it_ends_without_the_variable(tmp_path, monkeypatch):
    """Pascal ``uses util`` makes an edge with no target_file to util.pas's old file id. A JS
    variable ``pas`` in util.js spells that id. The edge must end exactly where the same
    edge ends when no such variable exists, never on the variable."""
    pas = {"uses/util.pas": "unit util;\ninterface\nimplementation\nend.\n",
           "uses/main.pas": "unit main;\ninterface\nuses util;\nimplementation\nend.\n"}
    contested = _run(tmp_path / "contested", {**pas, "uses/util.js": "function mk(){ return 1 }\nconst pas = mk();\n"}, monkeypatch)
    control = _run(tmp_path / "control", {**pas, "uses/util.js": "function mk(){ return 1 }\nconst other = mk();\n"}, monkeypatch)

    (target,) = [t for s, t in _edges(contested, "imports") if s == _node(contested, "main", "uses/main.pas")["id"]]
    (control_target,) = [t for s, t in _edges(control, "imports") if s == _node(control, "main", "uses/main.pas")["id"]]
    assert target == control_target
    assert target != _node(contested, "pas", "uses/util.js")["id"]


@pytest.mark.parametrize("name,mjs,expect", [
    ("other name", 'import postgres from "postgres";\nconst db = postgres(1);\nfunction prueba(){ return db }\n',
     {"x.mjs": "esquema_x_mjs_esquema_x", "db": "esquema_x_db", "x.sql": "esquema_x_sql_esquema_x"}),
    ("literal", "const sql = 1;\nfunction prueba(){ return sql }\n",
     {"x.mjs": "esquema_x_mjs_esquema_x", "x.sql": "esquema_x_sql_esquema_x"}),
])
def test_controls_with_a_sibling_keep_todays_ids(tmp_path, monkeypatch, name, mjs, expect):
    result = _run(tmp_path, {"esquema/x.mjs": mjs, "esquema/x.sql": SQL}, monkeypatch)
    got = {n["label"]: n["id"] for n in result["nodes"] if n["label"] in expect}
    assert got == expect, name


@pytest.mark.parametrize("sibling", [None, "esquema/y.sql"], ids=["no sibling", "other-stem sibling"])
def test_the_variable_beside_no_same_stem_sibling_keeps_todays_ids(tmp_path, monkeypatch, sibling):
    files = {"esquema/x.mjs": 'import postgres from "postgres";\nconst sql = postgres(1);\nfunction prueba(){ return sql }\n'}
    if sibling:
        files[sibling] = SQL
    result = _run(tmp_path, files, monkeypatch)
    assert _node(result, "x.mjs", "esquema/x.mjs")["id"] == "esquema_x"
    assert _node(result, "sql", "esquema/x.mjs")["id"] == "esquema_x_sql"


def test_a_stub_from_a_different_stem_keeps_todays_ids(tmp_path, monkeypatch):
    """A Lazarus package names a unit with the unit file's old id. Its stem differs
    from the unit's, so the key is not contested and nothing moves."""
    lpk = ('<?xml version="1.0"?>\n<CONFIG><Package Version="5"><Name Value="P"/><Files Count="1"><Item1>'
           '<Filename Value="b.pas"/><UnitName Value="b"/></Item1></Files></Package></CONFIG>\n')
    result = _run(tmp_path, {"lazarus/a.lpk": lpk, "lazarus/b.pas": "unit b;\ninterface\nimplementation\nend.\n"}, monkeypatch)
    assert _node(result, "b", "lazarus/a.lpk")["id"] == "lazarus_a_lpk_lazarus_b"
    assert _node(result, "b.pas", "lazarus/b.pas")["id"] == "lazarus_b_pas_lazarus_b"


def test_a_swift_type_named_like_the_sibling_extension_keeps_both_file_nodes(tmp_path, monkeypatch):
    """struct sql and ``extension sql`` in x.swift next to x.sql. The recorded extension nid must
    follow the type node. If it follows the file-level rename instead, _merge_swift_extensions
    removes every node with that id, and both file nodes go with it."""
    files = {"sw/x.swift": "struct sql {\n    func run() {}\n}\n\nextension sql {\n    func extra() {}\n}\n",
             "sw/x.sql": SQL}
    result = _run(tmp_path, files, monkeypatch)

    swift_file = _node(result, "x.swift", "sw/x.swift")["id"]
    sql_file = _node(result, "x.sql", "sw/x.sql")["id"]
    type_node = _node(result, "sql", "sw/x.swift")["id"]
    assert len({swift_file, sql_file, type_node}) == 3
    run, extra = _node(result, ".run()", "sw/x.swift")["id"], _node(result, ".extra()", "sw/x.swift")["id"]
    assert {(type_node, run), (type_node, extra)} <= set(_edges(result, "method"))
