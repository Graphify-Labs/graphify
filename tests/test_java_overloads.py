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
