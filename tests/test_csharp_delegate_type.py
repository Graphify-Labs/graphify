"""C# delegate declarations (#4552).

`delegate_declaration` was in neither `class_types` nor `function_types`, so
the declaration itself got no node. A field or parameter typed as the
delegate still resolved the name through `ensure_named_node`, which minted a
sourceless stub and pointed every `references` edge at that stub instead of
the real, same-file declaration.
"""
from __future__ import annotations

import os
from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files], cache_root=tmp_path / ".cache")
    finally:
        os.chdir(old)
    return r


def _edges(r, relation):
    return {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == relation}


def test_delegate_gets_a_sourced_node(tmp_path):
    r = _extract(tmp_path, {
        "Calc.cs": (
            "public delegate int BinOp(int a, int b);\n"
            "public class Calc {\n"
            "    public BinOp Op;\n"
            "    public int Apply(BinOp f, int x) { return f(x, x); }\n"
            "}\n"
        ),
    })
    delegate = next(n for n in r["nodes"] if n["label"] == "BinOp")
    assert delegate["source_file"], "the delegate must not be a sourceless stub"
    assert delegate["source_file"].endswith("Calc.cs")


def test_delegate_references_bind_to_the_real_node_not_a_stub(tmp_path):
    r = _extract(tmp_path, {
        "Calc.cs": (
            "public delegate int BinOp(int a, int b);\n"
            "public class Calc {\n"
            "    public BinOp Op;\n"
            "    public int Apply(BinOp f, int x) { return f(x, x); }\n"
            "}\n"
        ),
    })
    delegate = next(n for n in r["nodes"] if n["label"] == "BinOp")
    calc = next(n for n in r["nodes"] if n["label"] == "Calc")
    apply_fn = next(n for n in r["nodes"] if n["label"] == ".Apply()")
    refs = _edges(r, "references")
    assert (calc["id"], delegate["id"]) in refs
    assert (apply_fn["id"], delegate["id"]) in refs
    # Exactly one BinOp node exists -- the sourced one, not a second,
    # sourceless stub that references would otherwise collide onto.
    assert sum(1 for n in r["nodes"] if n["label"] == "BinOp") == 1


def test_delegate_is_contained_by_its_file(tmp_path):
    r = _extract(tmp_path, {
        "Calc.cs": "public delegate int BinOp(int a, int b);\n",
    })
    delegate = next(n for n in r["nodes"] if n["label"] == "BinOp")
    file_node = next(n for n in r["nodes"] if n["label"] == "Calc.cs")
    assert (file_node["id"], delegate["id"]) in _edges(r, "contains")
