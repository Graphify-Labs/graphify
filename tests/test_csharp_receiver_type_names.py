"""C# receivers whose type name does not start with a capital (#5174).

`_Pair` and `pair` are valid C# class names. Locals and parameters of such a
type are typed since #4849, but two paths still required an upper-case first
character: the field (and primary-constructor parameter) table, and the static
call `Type.M()`. So `_field.Swap()` on a `_Pair _field` and `pair.Create()`
got no calls edge.

The static path reads an undeclared receiver as a type name only when no
local, parameter, field or property of that name is in scope, typed or not.
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


_TYPES = (
    "namespace Demo {\n"
    "    public class _Pair {\n"
    "        public void Swap() { }\n"
    "        public static _Pair Make() { return new _Pair(); }\n"
    "    }\n"
    "    public class pair {\n"
    "        public void Flip() { }\n"
    "        public static pair Create() { return new pair(); }\n"
    "    }\n"
    "    public class Pair {\n"
    "        public void Swap() { }\n"
    "        public void Flip() { }\n"
    "    }\n"
    "}\n"
)


def _host(body: str, head: str = "public class Host") -> dict[str, str]:
    return {"Types.cs": _TYPES,
            "Host.cs": "namespace Demo {\n    " + head + " {\n" + body + "    }\n}\n"}


def test_field_of_underscore_type_types_its_receiver(tmp_path):
    r = _extract(tmp_path, _host(
        "        private _Pair _field;\n"
        "        public void Use() { _field.Swap(); }\n"))
    assert _call_targets(r, ".Use()") == {"_Pair.Swap()"}


def test_field_of_lowercase_type_types_its_receiver(tmp_path):
    r = _extract(tmp_path, _host(
        "        private pair _field;\n"
        "        public void Use() { _field.Flip(); }\n"))
    assert _call_targets(r, ".Use()") == {"pair.Flip()"}


def test_primary_constructor_parameter_of_lowercase_type(tmp_path):
    r = _extract(tmp_path, _host(
        "        public void Use() { p.Flip(); }\n",
        head="public class Host(pair p)"))
    assert _call_targets(r, ".Use()") == {"pair.Flip()"}


def test_static_call_on_underscore_and_lowercase_type(tmp_path):
    r = _extract(tmp_path, _host(
        "        public void UseA() { _Pair.Make(); }\n"
        "        public void UseB() { pair.Create(); }\n"))
    assert _call_targets(r, ".UseA()") == {"_Pair.Make()"}
    assert _call_targets(r, ".UseB()") == {"pair.Create()"}


def test_parameter_and_local_of_lowercase_type_still_bind(tmp_path):
    # Already fixed by #4849; kept so the static path cannot regress them.
    r = _extract(tmp_path, _host(
        "        public void UseA(_Pair p) { p.Swap(); }\n"
        "        public void UseB() { pair p = new pair(); p.Flip(); }\n"))
    assert _call_targets(r, ".UseA()") == {"_Pair.Swap()"}
    assert _call_targets(r, ".UseB()") == {"pair.Flip()"}


def test_declared_type_wins_over_a_same_named_lowercase_type(tmp_path):
    # The local `pair` is declared as `Pair`; the class `pair` must not capture it.
    r = _extract(tmp_path, _host(
        "        public void Use() { Pair pair = new Pair(); pair.Flip(); }\n"))
    assert _call_targets(r, ".Use()") == {"Pair.Flip()"}


def test_untyped_value_named_like_a_type_is_not_a_static_call(tmp_path):
    # A dynamic local and an untyped lambda parameter are values: `pair.Flip()`
    # on them must not bind to the class `pair`.
    r = _extract(tmp_path, _host(
        "        public void UseA(dynamic pair) { pair.Flip(); }\n"
        "        public void UseB() {\n"
        "            System.Action<object> f = pair => pair.Flip();\n"
        "        }\n"
        "        private dynamic _pair;\n"
        "        public void UseC() { _pair.Swap(); }\n"))
    assert _call_targets(r, ".UseA()") == set()
    assert _call_targets(r, ".UseB()") == set()
    assert _call_targets(r, ".UseC()") == set()


def test_prior_ast_cache_is_not_reused(tmp_path, monkeypatch):
    import graphify.cache as cache
    assert cache._AST_CACHE_SCHEMA > 44
    files = _host("        public void UseStatic() { pair.Create(); }\n")
    with monkeypatch.context() as old:
        old.setattr(cache, "_AST_CACHE_SCHEMA", 44)
        _extract(tmp_path, files)
        # Strip the new flag as if these entries predated this fix.
        for path in (tmp_path / ".cache").rglob("*.json"):
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace('"receiver_undeclared"', '"old_flag"'),
                            encoding="utf-8")
    r = _extract(tmp_path, files)
    assert _call_targets(r, ".UseStatic()") == {"pair.Create()"}


def test_builtin_receivers_stay_unbound(tmp_path):
    files = {
        "Text.cs": (
            "public class Text { public string Trim() => \"\"; public void Save() { } }\n"
        ),
        "Host.cs": (
            "public class Host {\n"
            "    private string _name;\n"
            "    public void UseString() { _name.Trim(); }\n"
            "}\n"
        ),
    }
    r = _extract(tmp_path, files)
    assert _call_targets(r, ".UseString()") == set()
