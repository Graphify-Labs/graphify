"""Go intra-module imports must reach the imported package's files (#3746).

`graphify/extractors/go.py` turns every `import "x/y"` into an `imports_from`
edge whose target id is minted from the raw string (`go_pkg_x_y`). That node
has no source file and nothing links it onward, so an importer never reaches
the package it depends on: `graphify affected <file>` misses every consumer
that arrives through an import, while qualified calls (`b.F()`) do resolve,
because the call pass filters callees by `_go_import_path_for_file`.

Measured on a 744-file module with a single go.mod: 0 of 21 direct intra-module
imports of a handler package resolved to files; 57 intra-module `go_pkg_*`
nodes had 780 edges in and 0 out.

The fix inverts the mapping the call pass already uses — every Go file's
canonical import path — and repoints the intra-module `imports_from` edges
onto that package's file nodes, the way the JS/TS resolver repoints module
specifiers. Stdlib and external imports have no file in the corpus and stay
sinks on purpose; the last test pins that.
"""
from pathlib import Path

from graphify.extract import extract


def _extract(root: Path) -> dict:
    return extract(
        sorted(root.rglob("*.go")),
        cache_root=root,
        root=root,
        parallel=False,
    )


def _file_node(result: dict, suffix: str) -> dict:
    hits = [
        n for n in result["nodes"]
        if str(n.get("source_file", "")).endswith(suffix)
        and n.get("label") == Path(suffix).name
    ]
    assert len(hits) == 1, f"expected one file node for {suffix}, got {hits}"
    return hits[0]


def _edges(result: dict, source_id: str, relation: str) -> list[dict]:
    return [
        e for e in result["edges"]
        if e.get("source") == source_id and e.get("relation") == relation
    ]


def _write_module(root: Path) -> None:
    (root / "go.mod").write_text("module example.com/m\n\ngo 1.22\n")
    a = root / "a"
    b = root / "b"
    a.mkdir()
    b.mkdir()
    (b / "b.go").write_text("package b\n\nfunc F() int { return 1 }\n")
    (b / "c.go").write_text("package b\n\nfunc G() int { return 2 }\n")
    (a / "a.go").write_text(
        "package a\n\n"
        'import (\n\t"fmt"\n\n\t"example.com/m/b"\n)\n\n'
        "func Run() int {\n\tfmt.Println(b.G())\n\treturn b.F()\n}\n"
    )


def test_intra_module_import_reaches_every_file_of_the_package(tmp_path: Path) -> None:
    _write_module(tmp_path)
    result = _extract(tmp_path)

    a_go = _file_node(result, "a/a.go")
    b_go = _file_node(result, "b/b.go")
    c_go = _file_node(result, "b/c.go")

    imports = _edges(result, a_go["id"], "imports_from")
    targets = {e["target"] for e in imports}
    assert b_go["id"] in targets, imports
    assert c_go["id"] in targets, imports
    # The synthetic sink for an intra-module package is gone: nothing points at it.
    assert "go_pkg_example_com_m_b" not in targets, imports
    assert not any(
        e["target"] == "go_pkg_example_com_m_b" for e in result["edges"]
    )


def test_repoint_keeps_the_call_edge_and_adds_no_self_import(tmp_path: Path) -> None:
    _write_module(tmp_path)
    result = _extract(tmp_path)

    a_go = _file_node(result, "a/a.go")
    run_ids = {n["id"] for n in result["nodes"] if n.get("label") == "Run()"}
    f_ids = {n["id"] for n in result["nodes"] if n.get("label") == "F()"}
    assert run_ids and f_ids
    assert any(
        e["source"] in run_ids and e["target"] in f_ids and e["relation"] == "calls"
        for e in result["edges"]
    ), "the qualified call edge must survive the import repoint"
    assert not any(
        e["source"] == a_go["id"] and e["target"] == a_go["id"]
        for e in result["edges"]
    )


def test_stdlib_and_external_imports_stay_sinks(tmp_path: Path) -> None:
    _write_module(tmp_path)
    result = _extract(tmp_path)

    a_go = _file_node(result, "a/a.go")
    imports = _edges(result, a_go["id"], "imports_from")
    fmt_targets = [e["target"] for e in imports if e["target"].startswith("go_pkg_fmt")]
    assert fmt_targets == ["go_pkg_fmt"], imports
    # No file in the corpus is "fmt", so the sink must not have been repointed.
    fmt_node = [n for n in result["nodes"] if n.get("id") == "go_pkg_fmt"]
    assert all(not n.get("source_file") for n in fmt_node)
