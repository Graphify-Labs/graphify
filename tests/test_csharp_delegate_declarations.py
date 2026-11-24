"""A C# `delegate` is a named type and must be extracted as a sourced node.

`public delegate int BinOp(int a, int b);` was in neither `class_types` nor
`function_types`, so the declaration was dropped. But a field or parameter typed
as the delegate (`BinOp Op;`) still ran the name `BinOp` through
`ensure_named_node`, which minted a *sourceless* stub node and pointed the
`references` edge at it — even though `BinOp` is declared in the very same file.
That is a provenance violation (a real source-backed declaration losing to a
sourceless god node). Adding `delegate_declaration` to the C# `class_types` emits
a clean empty type node (it has a `name` field and no body) that the in-file
references bind to instead.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path, body: str):
    (tmp_path / "d.cs").write_text(body)
    return extract([tmp_path / "d.cs"], cache_root=tmp_path, parallel=False)


def _node(r, label):
    return next((n for n in r["nodes"] if n.get("label") == label), None)


def test_delegate_is_a_sourced_node_not_a_sourceless_stub(tmp_path):
    r = _extract(
        tmp_path,
        "public delegate int BinOp(int a, int b);\n"
        "public class Calc {\n"
        "    public BinOp Op;\n"
        "    public int Apply(BinOp f, int x) { return f(x, x); }\n"
        "}\n",
    )
    binop = _node(r, "BinOp")
    assert binop is not None, "delegate declaration was dropped"
    assert binop.get("source_file"), (
        f"delegate BinOp is a sourceless god node: {binop}"
    )
    # No sourceless node is left over for a type that is declared in-file.
    assert not any(
        (not n.get("source_file")) and n.get("label") == "BinOp"
        for n in r["nodes"]
    )
    # The field/parameter references now bind to the real sourced delegate node.
    refs_to_binop = {
        e["source"]
        for e in r["edges"]
        if e["relation"] == "references" and e["target"] == binop["id"]
    }
    assert refs_to_binop, "references to the delegate did not bind to it"


def test_namespaced_delegate_is_scoped_and_sourced(tmp_path):
    r = _extract(
        tmp_path,
        "namespace App {\n"
        "    public delegate void Handler(string msg);\n"
        "    public class Bus { public Handler OnMsg; }\n"
        "}\n",
    )
    handler = _node(r, "Handler")
    assert handler is not None and handler.get("source_file")
    assert any(
        e["relation"] == "references" and e["target"] == handler["id"]
        for e in r["edges"]
    )
