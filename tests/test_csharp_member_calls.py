"""C# receiver-typed member-call resolution (#1609).

`recv.Method()` where `recv` is a typed field / property / parameter / local must
resolve to the receiver TYPE's method — not a bare same-named match. Before this,
C# had no member-call resolver: the bare method name matched any same-named method
in the corpus, so `_server.Save()` silently mis-bound to an unrelated `Cache.Save()`
(a WRONG edge, not just a missing one). Resolution is by receiver type with the
single-definition god-node guard; an untypable receiver produces no edge.
"""
from __future__ import annotations

import os
from pathlib import Path

from graphify.extract import extract


def _calls(tmp_path, files: dict[str, str]):
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
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    return calls, r


_AMBIG = {
    "S.cs": (
        "public class Server { public bool Save() => true; }\n"
        "public class Cache  { public bool Save() => false; }\n"
        "public class Repo {\n"
        "    private Server _server = new Server();\n"
        "    public bool Commit() { return _server.Save(); }\n"
        "}\n"
    )
}


def _find(r, label, id_contains):
    return next(n["id"] for n in r["nodes"]
               if n["label"] == label and id_contains in n["id"])


def test_field_receiver_resolves_to_declared_type_not_bare_match(tmp_path):
    calls, r = _calls(tmp_path, _AMBIG)
    commit = _find(r, ".Commit()", "commit")
    server_save = _find(r, ".Save()", "server")
    cache_save = _find(r, ".Save()", "cache")
    assert (commit, server_save) in calls, "field.Method() must resolve to the field's type"
    assert (commit, cache_save) not in calls, "must NOT mis-bind to an unrelated same-named method"


def test_parameter_receiver_resolves(tmp_path):
    calls, r = _calls(tmp_path, {
        "S.cs": (
            "public class Server { public bool Save() => true; }\n"
            "public class Cache  { public bool Save() => false; }\n"
            "public class Svc { public static bool Copy(Server server) { return server.Save(); } }\n"
        )
    })
    assert any("copy" in s and "server_save" in t for s, t in calls)
    assert not any("copy" in s and "cache_save" in t for s, t in calls)


def test_local_var_receiver_resolves(tmp_path):
    calls, r = _calls(tmp_path, {
        "S.cs": (
            "public class Server { public bool Save() => true; }\n"
            "public class R {\n"
            "    public bool A() { Server s = new Server(); return s.Save(); }\n"
            "    public bool B() { var v = new Server(); return v.Save(); }\n"
            "}\n"
        )
    })
    assert any("_r_a" in s and "server_save" in t for s, t in calls), "explicit-typed local"
    assert any("_r_b" in s and "server_save" in t for s, t in calls), "var = new T() local"


def test_cross_file_receiver_resolves(tmp_path):
    calls, r = _calls(tmp_path, {
        "Server.cs": (
            "public class Server { public bool Save() => true; }\n"
            "public class Cache  { public bool Save() => false; }\n"
        ),
        "Repo.cs": (
            "public class Repo { private Server _s = new Server(); "
            "public bool Commit() { return _s.Save(); } }\n"
        ),
    })
    assert any("commit" in s and "server_save" in t for s, t in calls)
    assert not any("commit" in s and "cache_save" in t for s, t in calls)


def test_this_and_static_receivers(tmp_path):
    calls, r = _calls(tmp_path, {
        "S.cs": (
            "public class Util { public static int F() => 1; }\n"
            "public class R {\n"
            "    public bool A() { return this.B(); }\n"
            "    public bool B() => true;\n"
            "    public int G() { return Util.F(); }\n"
            "}\n"
        )
    })
    assert any("_r_a" in s and "_r_b" in t for s, t in calls), "this.B() -> R.B"
    assert any("_r_g" in s and "util_f" in t for s, t in calls), "Util.F() -> Util.F"


def test_untyped_receiver_emits_no_edge(tmp_path):
    calls, r = _calls(tmp_path, {
        "S.cs": (
            "public class Server { public bool Save() => true; }\n"
            "public class R { public bool C(dynamic x) { return x.Save(); } }\n"
        )
    })
    assert not any("save" in t.lower() for _s, t in calls), "dynamic receiver must not resolve"


def test_method_absent_on_type_emits_no_edge(tmp_path):
    calls, r = _calls(tmp_path, {
        "S.cs": (
            "public class Server { public bool Save() => true; }\n"
            "public class R { private Server _s = new Server(); "
            "public bool C() { return _s.Missing(); } }\n"
        )
    })
    assert not any("_r_c" in s and "save" in t.lower() for s, t in calls)


def test_unqualified_call_still_resolves(tmp_path):
    calls, r = _calls(tmp_path, {
        "S.cs": (
            "public class R { public bool A() { Helper(); return true; } "
            "private void Helper() {} }\n"
        )
    })
    assert any("_r_a" in s and "helper" in t for s, t in calls), "no regression on unqualified calls"


def test_method_chained_off_new_expression_resolves(tmp_path):
    """#1770: a method invoked directly on a `new X(...)` object-creation
    expression (no intermediate variable) must still emit a calls edge to the
    constructed type's method — the fluent `new X(...).M()` pattern."""
    calls, r = _calls(tmp_path, {
        "S.cs": (
            "public class Merger {\n"
            "    public Merger(int x) {}\n"
            "    public int Combine(int a, bool b) { return a; }\n"
            "}\n"
            "public class Svc {\n"
            "    public int Run(int ctx) {\n"
            "        return new Merger(ctx).Combine(ctx, true);\n"
            "    }\n"
            "}\n"
        )
    })
    label = {n["id"]: n.get("label") for n in r["nodes"]}
    assert any(
        "run" in s and label.get(t) == ".Combine()"
        for s, t in calls
    ), f"chained call off new Merger(...) not captured: {[(s, label.get(t)) for s, t in calls]}"
