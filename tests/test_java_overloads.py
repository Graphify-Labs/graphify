"""Java overloads get a node each, and calls pick theirs by argument count (#5251).

Overloads share a name, so they minted one id: ``add_node`` kept the first
declaration and the others vanished, so every caller of any overload pointed at
the first one. The first declared overload keeps the plain id (a class without
overloads, and the first overload, keep the ids they had) and every other
signature gets a salted one. A call binds to the overload its argument count
fits; when that is not unique (``run(String)`` / ``run(int)``) it binds to the
first declared one, as before.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from graphify.extract import extract

_SVC = """class Svc {
  void run(String s) { helperOne(); }
  void run(int i) { helperTwo(); }
  void run(String s, int i) { helperThree(); }
  void helperOne() {}
  void helperTwo() {}
  void helperThree() {}
}
"""

_ARITY = """class Greeter {
  String greet() { return greet("a"); }
  String greet(String name) { return greet(name, 1); }
  String greet(String name, int times) { return name; }
}
"""

_CALLER = """class Caller {
  void one(Svc svc) { svc.run("x"); }
  void two(Svc svc) { svc.run("x", 1); }
}
"""


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        return extract([Path(n) for n in files], cache_root=Path(tempfile.mkdtemp()))
    finally:
        os.chdir(old)


def _methods(r, label):
    return {
        n["source_location"]: n
        for n in r["nodes"] if n["label"] == label and n.get("source_file")
    }


def _calls(r):
    return {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}


def test_each_overload_is_its_own_node(tmp_path):
    r = _extract(tmp_path, {"Svc.java": _SVC})
    runs = _methods(r, ".run()")
    assert sorted(runs) == ["L2", "L3", "L4"]
    assert len({n["id"] for n in runs.values()}) == 3
    assert all(e["target"] in {n["id"] for n in r["nodes"]} for e in r["edges"])


def test_first_overload_keeps_the_plain_id(tmp_path):
    r = _extract(tmp_path, {"Svc.java": _SVC})
    runs = _methods(r, ".run()")
    plain = runs["L2"]["id"]
    assert plain.endswith("svc_run")
    assert runs["L3"]["id"].startswith(plain + "_")


def test_overload_signature_metadata(tmp_path):
    r = _extract(tmp_path, {"Svc.java": _SVC})
    runs = _methods(r, ".run()")
    assert runs["L2"]["metadata"]["arity"] == 1
    assert runs["L4"]["metadata"]["arity"] == 2
    assert runs["L2"]["metadata"]["signature"] == "String"
    assert runs["L3"]["metadata"]["signature"] == "int"
    assert runs["L4"]["metadata"]["signature"] == "String,int"


def test_each_overload_owns_its_own_calls(tmp_path):
    r = _extract(tmp_path, {"Svc.java": _SVC})
    runs = _methods(r, ".run()")
    by_label = {n["label"]: n["id"] for n in r["nodes"] if n.get("source_file")}
    calls = _calls(r)
    assert (runs["L2"]["id"], by_label[".helperOne()"]) in calls
    assert (runs["L3"]["id"], by_label[".helperTwo()"]) in calls
    assert (runs["L4"]["id"], by_label[".helperThree()"]) in calls


def test_same_file_call_binds_by_argument_count(tmp_path):
    r = _extract(tmp_path, {"Greeter.java": _ARITY})
    g = _methods(r, ".greet()")
    calls = _calls(r)
    assert (g["L2"]["id"], g["L3"]["id"]) in calls
    assert (g["L3"]["id"], g["L4"]["id"]) in calls
    assert (g["L2"]["id"], g["L4"]["id"]) not in calls


def test_cross_file_member_call_binds_by_argument_count(tmp_path):
    r = _extract(tmp_path, {"Svc.java": _SVC, "Caller.java": _CALLER})
    runs = _methods(r, ".run()")
    by_label = {n["label"]: n["id"] for n in r["nodes"] if n.get("source_file")}
    calls = _calls(r)
    assert (by_label[".two()"], runs["L4"]["id"]) in calls
    assert (by_label[".two()"], runs["L2"]["id"]) not in calls
    # `run("x")` fits run(String) and run(int) by count: first declared, as before.
    assert (by_label[".one()"], runs["L2"]["id"]) in calls


def test_varargs_overload_accepts_extra_arguments(tmp_path):
    src = """class V {
  void log(String fmt, Object... args) {}
  void log(String a) {}
  void use() { log("a", 1, 2); }
}
"""
    r = _extract(tmp_path, {"V.java": src})
    logs = _methods(r, ".log()")
    use = next(n["id"] for n in r["nodes"] if n["label"] == ".use()")
    assert (use, logs["L2"]["id"]) in _calls(r)
    assert logs["L2"]["metadata"]["variadic"] is True


def test_generics_are_erased_in_the_signature(tmp_path):
    src = """import java.util.List;
class G {
  void put(List<String> xs) {}
  void put(List<Integer> xs, int n) {}
}
"""
    r = _extract(tmp_path, {"G.java": src})
    puts = _methods(r, ".put()")
    assert puts["L3"]["metadata"]["signature"] == "List"
    assert puts["L4"]["metadata"]["signature"] == "List,int"


def test_non_overloaded_ids_are_unchanged(tmp_path):
    r = _extract(tmp_path, {"Svc.java": _SVC})
    ids = {n["label"]: n["id"] for n in r["nodes"] if n["label"] == ".helperOne()"}
    assert ids[".helperOne()"].endswith("svc_helperone")


_FACTORY = """class Product { void ship() {} }
class Factory {
  static Product make() { return null; }
  static Product make(int n) { return null; }
}
"""

_CHAIN_CALLER = """class Shop {
  void one() { Factory.make(1).ship(); }
  void none() { Factory.make().ship(); }
}
"""


def test_chained_call_through_an_overloaded_method_keeps_its_edge(tmp_path):
    """`Factory.make(1).ship()`: the intermediate `make` is picked by its own
    argument count, so the chain still types `ship` to Product."""
    r = _extract(tmp_path, {"Factory.java": _FACTORY, "Shop.java": _CHAIN_CALLER})
    by_label = {n["label"]: n["id"] for n in r["nodes"] if n.get("source_file")}
    calls = _calls(r)
    assert (by_label[".one()"], by_label[".ship()"]) in calls
    assert (by_label[".none()"], by_label[".ship()"]) in calls


_RUNNERS = """class Runner {
  void run() {}
  void run(String s) {}
  void run(int i) {}
}
"""

_RUN_CALLER = """class Use {
  void go(Runner r) { r.run("x"); }
}
"""


def test_ambiguous_member_call_binds_to_the_first_declared_overload(tmp_path):
    """`run(String)` and `run(int)` both fit one argument: the first declared
    overload (`run()`) stands for the name, the policy the same-file walk and the
    bare-name fallback use, not the first of those that fit."""
    r = _extract(tmp_path, {"Runner.java": _RUNNERS, "Use.java": _RUN_CALLER})
    runs = _methods(r, ".run()")
    go = next(n["id"] for n in r["nodes"] if n["label"] == ".go()")
    calls = _calls(r)
    assert (go, runs["L2"]["id"]) in calls
    assert (go, runs["L3"]["id"]) not in calls


def test_overloads_with_differently_bounded_type_variables_are_distinct(tmp_path):
    """`<T extends Number> run(T)` and `<T extends CharSequence> run(T)` erase to
    `Number` and `CharSequence`, so they are two overloads, each owning its body."""
    src = """class G {
  <T extends Number> void run(T x) { a(); }
  <T extends CharSequence> void run(T x) { b(); }
  void a() {}
  void b() {}
}
"""
    r = _extract(tmp_path, {"G.java": src})
    runs = _methods(r, ".run()")
    assert sorted(runs) == ["L2", "L3"]
    assert runs["L2"]["metadata"]["signature"] == "Number"
    assert runs["L3"]["metadata"]["signature"] == "CharSequence"
    by_label = {n["label"]: n["id"] for n in r["nodes"] if n.get("source_file")}
    calls = _calls(r)
    assert (runs["L2"]["id"], by_label[".a()"]) in calls
    assert (runs["L3"]["id"], by_label[".b()"]) in calls


def test_type_variable_erasure_rules(tmp_path):
    src = """class Box<B extends Number> {
  <T extends Number & Comparable<T>> void m(T x, B b, T[] ys, T... zs) {}
  <U> void f(U u) {}
  <A, C extends A> void g(C c) {}
}
"""
    r = _extract(tmp_path, {"Box.java": src})
    sigs = {n["label"] + n["source_location"]: n["metadata"]["signature"]
            for n in r["nodes"] if n.get("source_file") and "signature" in (n.get("metadata") or {})}
    assert sigs[".m()L2"] == "Number,Number,Number[],Number..."
    assert sigs[".f()L3"] == "Object"      # no bound -> Object
    assert sigs[".g()L4"] == "Object"      # C extends A, A unbounded


def test_bare_kotlin_call_to_an_overloaded_java_method_keeps_its_edge(tmp_path):
    """`run("x")` inside a Kotlin subclass of a Java class: the call has no
    argument count, so the first declared overload stands for the name."""
    base = """package p;
public class Base {
  public void run(String s) {}
  public void run(int a, int b) {}
}
"""
    sub = """package q
import p.Base
class Sub : Base() {
  fun go() { run("x") }
}
"""
    r = _extract(tmp_path, {"p/Base.java": base, "q/Sub.kt": sub})
    runs = _methods(r, ".run()")
    go = next(n["id"] for n in r["nodes"] if n["label"] == ".go()")
    assert (go, runs["L3"]["id"]) in _calls(r)


def test_class_bounds_are_resolved_before_a_method_type_variable_shadows_them(tmp_path):
    """`U extends T` names the class's `T` (a Number); the method's own
    `<T extends CharSequence>` shadows `T` only for what the method declares
    itself. `run(U)` therefore erases to `Number`, not `CharSequence`, and the two
    overloads stay two nodes."""
    src = """class G<T extends Number, U extends T> {
  <T extends CharSequence> void run(U x) { a(); }
  void run(CharSequence x) { b(); }
  void a() {}
  void b() {}
}
"""
    r = _extract(tmp_path, {"G.java": src})
    runs = _methods(r, ".run()")
    assert sorted(runs) == ["L2", "L3"]
    assert runs["L2"]["metadata"]["signature"] == "Number"
    assert runs["L3"]["metadata"]["signature"] == "CharSequence"
    by_label = {n["label"]: n["id"] for n in r["nodes"] if n.get("source_file")}
    calls = _calls(r)
    assert (runs["L2"]["id"], by_label[".a()"]) in calls
    assert (runs["L3"]["id"], by_label[".b()"]) in calls


def test_a_bound_may_name_a_later_variable_of_the_same_scope(tmp_path):
    src = """class H {
  <A extends B, B extends Number> void m(A a) {}
}
"""
    r = _extract(tmp_path, {"H.java": src})
    assert _methods(r, ".m()")["L2"]["metadata"]["signature"] == "Number"
