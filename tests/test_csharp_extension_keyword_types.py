"""C# extension calls on keyword-typed receivers (#5174).

`bool` and `System.Boolean` are one type, but the extension pass compared the
names as text, so `b.ToVis()` on a `bool b` never bound `ToVis(this Boolean)`.
And `c.Value.IsWs()` on a `char? c` was dropped as an untyped `x.F.M()` chain,
although a keyword value type has no `Value` member: it is `Nullable<T>.Value`,
typed T.
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
        return extract([Path(n) for n in files], cache_root=tmp_path / ".cache")
    finally:
        os.chdir(old)


def _call_targets(r, caller_label: str) -> set[str]:
    """`Type.Method()` for every call edge leaving the method `caller_label`."""
    nodes = {n["id"]: n for n in r["nodes"]}
    owner = {e["target"]: nodes[e["source"]]["label"]
             for e in r["edges"] if e["relation"] == "method"}
    callers = {i for i, n in nodes.items() if n["label"] == caller_label}
    return {f"{owner.get(e['target'], '?')}{nodes[e['target']]['label']}"
            for e in r["edges"]
            if e["relation"] == "calls" and e["source"] in callers
            and nodes[e["target"]]["label"].startswith(".")}


_EXT = (
    "namespace Demo {\n"
    "    public static class BoolExt {\n"
    "        public static int ToVis(this System.Boolean v) { return 0; }\n"
    "    }\n"
    "    public static class CharExt {\n"
    "        public static bool IsWs(this char c) { return false; }\n"
    "    }\n"
    "    public static class IntExt {\n"
    "        public static int Twice(this Int32 i) { return i; }\n"
    "    }\n"
    "}\n"
)


def _host(body: str, extra: str = "") -> dict[str, str]:
    return {"Ext.cs": _EXT,
            "Host.cs": "namespace Demo {\n" + extra
            + "    public class Host {\n" + body + "    }\n}\n"}


def test_keyword_receiver_binds_system_type_extension(tmp_path):
    r = _extract(tmp_path, _host(
        "        private bool _flag;\n"
        "        public void UseLocal() { bool b = true; b.ToVis(); }\n"
        "        public void UseField() { _flag.ToVis(); }\n"))
    assert _call_targets(r, ".UseLocal()") == {"BoolExt.ToVis()"}
    assert _call_targets(r, ".UseField()") == {"BoolExt.ToVis()"}


def test_system_type_receiver_binds_keyword_extension(tmp_path):
    r = _extract(tmp_path, _host(
        "        public void Use(System.Char c) { c.IsWs(); }\n"))
    assert _call_targets(r, ".Use()") == {"CharExt.IsWs()"}


def test_nullable_value_of_keyword_type_binds_extension(tmp_path):
    r = _extract(tmp_path, _host(
        "        private char? _ch;\n"
        "        public void UseLocal() { char? c = 'a'; c.Value.IsWs(); }\n"
        "        public void UseField() { _ch.Value.IsWs(); }\n"))
    assert _call_targets(r, ".UseLocal()") == {"CharExt.IsWs()"}
    assert _call_targets(r, ".UseField()") == {"CharExt.IsWs()"}


def test_corpus_type_named_like_a_system_type_is_not_aliased(tmp_path):
    # The corpus declares its own `Int32`: `this Int32` extends that type, not
    # `int`, so an `int` receiver must not bind it.
    r = _extract(tmp_path, _host(
        "        public void Use() { int i = 1; i.Twice(); }\n",
        extra="    public class Int32 { }\n"))
    assert _call_targets(r, ".Use()") == set()


def test_value_member_of_a_corpus_type_is_not_nullable_value(tmp_path):
    # The corpus declares its own `Char` with a real `Value` property:
    # `c.Value.IsWs()` is that property, not `Nullable<char>.Value`.
    r = _extract(tmp_path, _host(
        "        public void Use(Char c) { c.Value.IsWs(); }\n",
        extra="    public class Char { public object Value { get; set; } }\n"))
    assert _call_targets(r, ".Use()") == set()
