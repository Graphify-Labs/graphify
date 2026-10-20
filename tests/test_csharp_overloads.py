"""C# overloads get a node each, and calls pick theirs by argument count (#4584).

Overloads share a name, so they minted one id: ``add_node`` kept the first
declaration, the others vanished, every caller of any overload pointed at the
first one, and a later overload's own calls were credited to it. Now the first
declared overload keeps the plain id (so a type without overloads, and the
first overload, keep the ids they had) and every other signature gets a salted
one. A call binds to the overload its argument count fits; when that is not
unique (``M(int)`` / ``M(string)``) it binds to the first, as before.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from graphify.extract import extract

_MESSAGES = """namespace Demo
{
    public static class Messages
    {
        public static string Banner(int code)
        {
            return Format(code);
        }

        public static string Banner(int code, string format)
        {
            return Pad(format);
        }

        private static string Format(int code) { return code.ToString(); }
        private static string Pad(string text) { return text; }
    }
}
"""

_CALLER = """namespace Demo
{
    public class Caller
    {
        public string OneArg() { return Messages.Banner(1); }
        public string TwoArgs() { return Messages.Banner(1, "x"); }
    }
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


def _by_line(r, label):
    return {
        n["source_location"]: n["id"]
        for n in r["nodes"] if n["label"] == label and n.get("source_file")
    }


def _edges(r, relation="calls"):
    return {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == relation}


def _id(r, label):
    ids = [n["id"] for n in r["nodes"] if n["label"] == label and n.get("source_file")]
    assert len(ids) == 1, (label, ids)
    return ids[0]


def test_issue_repro_each_overload_keeps_its_node_callers_and_callees(tmp_path):
    r = _extract(tmp_path, {"Messages.cs": _MESSAGES, "Caller.cs": _CALLER})
    banner = _by_line(r, ".Banner()")
    assert set(banner) == {"L5", "L10"}
    one, two = banner["L5"], banner["L10"]
    # The first overload keeps the id the single node had.
    assert one == "messages_demo_messages_banner"
    calls = _edges(r)
    assert (_id(r, ".OneArg()"), one) in calls
    assert (_id(r, ".TwoArgs()"), two) in calls
    assert (_id(r, ".OneArg()"), two) not in calls
    assert (_id(r, ".TwoArgs()"), one) not in calls
    assert (one, _id(r, ".Format()")) in calls
    assert (two, _id(r, ".Pad()")) in calls
    assert (one, _id(r, ".Pad()")) not in calls


def test_method_without_overloads_is_unchanged(tmp_path):
    r = _extract(tmp_path, {"Messages.cs": _MESSAGES})
    fmt = next(n for n in r["nodes"] if n["label"] == ".Format()")
    assert fmt["id"] == "messages_demo_messages_format"


def test_in_file_and_instance_calls_pick_by_argument_count(tmp_path):
    r = _extract(tmp_path, {
        "Svc.cs": (
            "public class Svc {\n"
            "    public void Run() { }\n"
            "    public void Run(int a) { Run(); }\n"
            "    public void Twice() { Run(1); }\n"
            "}\n"
        ),
        "Use.cs": (
            "public class Use {\n"
            "    public void Go(Svc s) { s.Run(); }\n"
            "    public void Go1(Svc s) { s.Run(2); }\n"
            "}\n"
        ),
    })
    run = _by_line(r, ".Run()")
    calls = _edges(r)
    assert (run["L3"], run["L2"]) in calls
    assert (_id(r, ".Twice()"), run["L3"]) in calls
    assert (_id(r, ".Twice()"), run["L2"]) not in calls
    assert (_id(r, ".Go()"), run["L2"]) in calls
    assert (_id(r, ".Go1()"), run["L3"]) in calls


def test_same_count_overloads_bind_to_the_first(tmp_path):
    r = _extract(tmp_path, {"S.cs": (
        "public static class S {\n"
        "    public static void Put(int x) { }\n"
        "    public static void Put(string x) { }\n"
        "    public static void Call() { Put(1); }\n"
        "}\n"
    )})
    put = _by_line(r, ".Put()")
    assert len(put) == 2
    calls = _edges(r)
    assert (_id(r, ".Call()"), put["L2"]) in calls
    assert (_id(r, ".Call()"), put["L3"]) not in calls


def test_optional_and_params_arguments_count(tmp_path):
    r = _extract(tmp_path, {"S.cs": (
        "public static class S {\n"
        "    public static void Opt(string s) { }\n"
        "    public static void Opt(int a, int b, int c = 1) { }\n"
        "    public static void Many(int a) { }\n"
        "    public static void Many(int a, int b, params int[] rest) { }\n"
        "    public static void Call() { Opt(1, 2); Many(1, 2, 3, 4); }\n"
        "}\n"
    )})
    calls = _edges(r)
    caller = _id(r, ".Call()")
    assert (caller, _by_line(r, ".Opt()")["L3"]) in calls
    assert (caller, _by_line(r, ".Many()")["L5"]) in calls


def test_same_file_partial_halves_keep_their_overloads(tmp_path):
    r = _extract(tmp_path, {"P.cs": (
        "public partial class P { public void M(int a) { } }\n"
        "public partial class P { public void M(int a, int b) { M(a); } }\n"
    )})
    m = _by_line(r, ".M()")
    assert set(m) == {"L1", "L2"}
    assert (m["L2"], m["L1"]) in _edges(r)


def test_identical_signature_behind_preprocessor_stays_one_node(tmp_path):
    r = _extract(tmp_path, {"S.cs": (
        "public class S {\n"
        "#if A\n"
        "    public void M(int a) { }\n"
        "#else\n"
        "    public void M(int a) { }\n"
        "#endif\n"
        "}\n"
    )})
    assert len(_by_line(r, ".M()")) == 1


def test_interface_overloads_dispatch_to_their_own_implementation(tmp_path):
    r = _extract(tmp_path, {"S.cs": (
        "public interface IR { void M(int a); void M(int a, string b); }\n"
        "public class A : IR {\n"
        "    public void M(int a) { }\n"
        "    public void M(int a, string b) { }\n"
        "}\n"
    )})
    iface = _by_line(r, ".M()")
    dispatch = _edges(r, "dispatches_to")
    ir1 = next(n["id"] for n in r["nodes"] if n["id"].startswith("s_ir_m") and n["source_location"] == "L1"
               and n["metadata"].get("arity") == 1)
    ir2 = next(n["id"] for n in r["nodes"] if n["id"].startswith("s_ir_m")
               and n["metadata"].get("arity") == 2)
    assert dispatch == {(ir1, iface["L3"]), (ir2, iface["L4"])}


def test_overload_ids_ignore_whitespace_and_line_endings(tmp_path):
    src = (
        "public class S {\n"
        "    public void M(int a) { }\n"
        "    public void M(System.Collections.Generic.Dictionary<string, int> d) { }\n"
        "}\n"
    )
    a = _extract(tmp_path / "a", {"S.cs": src})
    b = _extract(tmp_path / "b", {"S.cs": src.replace(", int>", ",\n        int>").replace("\n", "\r\n")})
    assert sorted(_by_line(a, ".M()").values()) == sorted(_by_line(b, ".M()").values())


def test_interface_overload_implemented_on_a_base_does_not_dispatch_to_a_sibling(tmp_path):
    # Impl declares only M(int); M(string) comes from Base. IR.M(string) must
    # not be pinned on Impl.M(int) just because both take one argument.
    r = _extract(tmp_path, {"D.cs": (
        "public interface IR { void M(int a); void M(string a); }\n"
        "public class Base { public void M(string a) { } }\n"
        "public class Impl : Base, IR { public void M(int a) { } }\n"
    )})
    by_sig = {
        n["metadata"].get("signature"): n["id"]
        for n in r["nodes"] if n["id"].startswith("d_ir_m")
    }
    impl = next(n["id"] for n in r["nodes"] if n["id"] == "d_impl_m")
    assert _edges(r, "dispatches_to") == {(by_sig["int"], impl)}


def test_collapse_keeps_distinct_names_on_one_type_apart(tmp_path):
    # Review: overloads are folded per owner type, but only among candidates
    # of one name, so `Put` / `_Put` / `put` stay separate targets.
    r = _extract(tmp_path, {
        "A.cs": (
            "public partial class S {\n"
            "    public void Put(int a) { }\n"
            "    public void _Put(int a, int b) { }\n"
            "    public void put(int a, int b, int c) { }\n"
            "    public void Put(string a, int b) { }\n"
            "}\n"
        ),
        "B.cs": (
            "public partial class S {\n"
            "    public void Go() { Put(1); _Put(1, 2); put(1, 2, 3); Put(\"x\", 1); }\n"
            "}\n"
        ),
    })
    go = _id(r, ".Go()")
    calls = {t for s, t in _edges(r) if s == go}
    put = _by_line(r, ".Put()")
    assert calls == {put["L2"], put["L5"], _id(r, "._Put()"), _id(r, ".put()")}


def test_params_parameter_is_variadic_and_optional(tmp_path):
    r = _extract(tmp_path, {"P.cs": (
        "public static class P {\n"
        "    public static void Log(string m) { }\n"
        "    public static void Log(string m, params object[] args) { }\n"
        "}\n"
    )})
    meta = {n["source_location"]: n["metadata"] for n in r["nodes"] if n["label"] == ".Log()"}
    assert meta["L3"]["arity"] == 2 and meta["L3"]["min_arity"] == 1 and meta["L3"]["variadic"]
    assert "variadic" not in meta["L2"]


def test_overloads_in_struct_record_and_beside_other_members(tmp_path):
    r = _extract(tmp_path, {"L.cs": (
        "public struct St { public void M(int a) { } public int M2 { get; } public void M(int a, int b) { } }\n"
        "public record R { public void N() { } class Inner { public void N(int x) { } } public void N(int x) { } }\n"
    )})
    assert len([n for n in r["nodes"] if n["id"].startswith("l_st_m") and n["label"] == ".M()"]) == 2
    assert {n["id"] for n in r["nodes"] if n["label"] == ".N()"} == {"l_r_n", "l_r_n_46f8ab", "l_inner_n"}
