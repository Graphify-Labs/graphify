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


# ── Namespace-aware receiver typing + shadow poisoning (#1620) ────────────────

_NS_AB = {
    "A.cs": "namespace A { public class Svc { public bool Do() => true; } }\n",
    "B.cs": "namespace B { public class Svc { public bool Do() => false; } }\n",
}


def test_namespace_using_directive_disambiguates_receiver_type(tmp_path):
    """`Svc` exists in namespaces A and B; a caller file `using A;` must bind an
    `A.Svc`-typed receiver to A.Svc.Do — before #1620 the corpus-wide bare-name
    ambiguity made the resolver bail (missing edge)."""
    calls, r = _calls(tmp_path, {
        **_NS_AB,
        "Caller.cs": (
            "using A;\n"
            "namespace App {\n"
            "    public class Runner { public bool Go(Svc s) { return s.Do(); } }\n"
            "}\n"
        ),
    })
    a_do = _find(r, ".Do()", "a_a_svc")
    b_do = _find(r, ".Do()", "b_b_svc")
    runner_go = _find(r, ".Go()", "runner")
    assert (runner_go, a_do) in calls, "using A; must resolve Svc to A.Svc"
    assert (runner_go, b_do) not in calls, "must NOT bind to the same-named B.Svc"


def test_namespace_using_directive_resolves_to_other_namespace(tmp_path):
    calls, r = _calls(tmp_path, {
        **_NS_AB,
        "Caller.cs": (
            "using B;\n"
            "namespace App {\n"
            "    public class Runner { public bool Go(Svc s) { return s.Do(); } }\n"
            "}\n"
        ),
    })
    a_do = _find(r, ".Do()", "a_a_svc")
    b_do = _find(r, ".Do()", "b_b_svc")
    runner_go = _find(r, ".Go()", "runner")
    assert (runner_go, b_do) in calls, "using B; must resolve Svc to B.Svc"
    assert (runner_go, a_do) not in calls


def test_namespace_ambiguous_without_using_bails(tmp_path):
    """No using directive and `Svc` in two foreign namespaces: genuinely
    ambiguous — no edge to either candidate (never a guess)."""
    calls, r = _calls(tmp_path, {
        **_NS_AB,
        "Caller.cs": (
            "namespace App {\n"
            "    public class Runner { public bool Go(Svc s) { return s.Do(); } }\n"
            "}\n"
        ),
    })
    assert not any("runner" in s and "svc_do" in t for s, t in calls), \
        "ambiguous cross-namespace type must produce no edge"


def test_same_namespace_receiver_resolves_without_using(tmp_path):
    """A caller in namespace A resolves `Svc` to A.Svc even though B.Svc also
    exists — same-namespace visibility needs no using directive."""
    calls, r = _calls(tmp_path, {
        **_NS_AB,
        "A2.cs": (
            "namespace A {\n"
            "    public class Client { public bool Go(Svc s) { return s.Do(); } }\n"
            "}\n"
        ),
    })
    a_do = _find(r, ".Do()", "a_a_svc")
    b_do = _find(r, ".Do()", "b_b_svc")
    client_go = _find(r, ".Go()", "client")
    assert (client_go, a_do) in calls
    assert (client_go, b_do) not in calls


def test_local_shadowing_field_of_different_type_poisons_name(tmp_path):
    """A local `Other x` shadowing a field `Server x` makes the name's type
    conflicting — the binding is poisoned and `x.Run()` emits NO edge, instead
    of first-binding-wins mis-binding to Server.Run (a wrong edge)."""
    calls, r = _calls(tmp_path, {
        "S.cs": (
            "public class Server { public bool Run() => true; }\n"
            "public class Other  { public bool Run() => false; }\n"
            "public class Holder {\n"
            "    private Server x = new Server();\n"
            "    public bool A() { Other x = new Other(); return x.Run(); }\n"
            "}\n"
        )
    })
    holder_a = _find(r, ".A()", "holder")
    server_run = _find(r, ".Run()", "server")
    other_run = _find(r, ".Run()", "other")
    assert (holder_a, server_run) not in calls, \
        "shadowed field's type must not win (wrong edge)"
    assert (holder_a, other_run) not in calls, \
        "conflicting bindings poison the name entirely (conservative: no edge)"


def test_untyped_redeclaration_poisons_typed_field(tmp_path):
    """`var x = Compute();` (untypable) redeclaring a typed field poisons the
    name: `x.Run()` must not bind to the field's type."""
    calls, r = _calls(tmp_path, {
        "S.cs": (
            "public class Server { public bool Run() => true; }\n"
            "public class Holder {\n"
            "    private Server x = new Server();\n"
            "    public object Compute() => new object();\n"
            "    public bool A() { var x = Compute(); return x.Run(); }\n"
            "}\n"
        )
    })
    assert not any("holder_a" in s and "run" in t.lower() for s, t in calls)


def test_this_field_receiver_resolves(tmp_path):
    """`this._s.Save()` types the field exactly like a bare `_s.Save()`."""
    calls, r = _calls(tmp_path, {
        "S.cs": (
            "public class Server { public bool Save() => true; }\n"
            "public class Cache  { public bool Save() => false; }\n"
            "public class Repo {\n"
            "    private Server _s = new Server();\n"
            "    public bool Commit() { return this._s.Save(); }\n"
            "}\n"
        )
    })
    commit = _find(r, ".Commit()", "commit")
    server_save = _find(r, ".Save()", "server")
    cache_save = _find(r, ".Save()", "cache")
    assert (commit, server_save) in calls
    assert (commit, cache_save) not in calls


def test_base_receiver_resolves_to_base_class_method(tmp_path):
    calls, r = _calls(tmp_path, {
        "Base.cs": "public class BaseSvc { public bool Ping() => true; }\n",
        "Sub.cs": (
            "public class Sub : BaseSvc {\n"
            "    public bool Go() { return base.Ping(); }\n"
            "}\n"
        ),
    })
    sub_go = _find(r, ".Go()", "sub")
    ping = _find(r, ".Ping()", "basesvc")
    assert (sub_go, ping) in calls, "base.Ping() must resolve to the base class method"


def test_inherited_method_resolves_through_base_chain(tmp_path):
    """A method not declared on the receiver's type but inherited from a
    resolvable in-corpus base resolves to the base's declaration."""
    calls, r = _calls(tmp_path, {
        "S.cs": (
            "public class BaseSvc { public bool Ping() => true; }\n"
            "public class Derived : BaseSvc { }\n"
            "public class User {\n"
            "    public bool Use(Derived d) { return d.Ping(); }\n"
            "}\n"
        )
    })
    use = _find(r, ".Use()", "user")
    ping = _find(r, ".Ping()", "basesvc")
    assert (use, ping) in calls


def test_unresolved_base_poisons_inherited_member_lookup(tmp_path):
    """The receiver's type inherits from an out-of-corpus base: a method missing
    on the type may live on that base, so the lookup is poisoned — and it must
    NOT fall back to an unrelated same-named in-corpus method."""
    calls, r = _calls(tmp_path, {
        "S.cs": (
            "public class Server { public bool Save() => true; }\n"
            "public class Ext : NotInCorpus { }\n"
            "public class User {\n"
            "    public bool U(Ext e) { return e.Save(); }\n"
            "}\n"
        )
    })
    assert not any("user_u" in s and "save" in t.lower() for s, t in calls), \
        "unresolved base chain must bail, not mis-bind to Server.Save"


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
