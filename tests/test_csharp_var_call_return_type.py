"""C# `var x = R.M<A>(...)` is typed from M's declared return type (#4266).

`var report = ServiceFactory.Get<IReport>(scope); report.Build()` had no calls
edge because a `var` was only typed from `new T()`. The variable now takes the
called method's return type, with call-site type arguments substituted, when
the method resolves to exactly one declaration. Anything else stays untyped.
"""
from __future__ import annotations

import os
from pathlib import Path

from graphify.extract import extract


def _calls(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        (tmp_path / name).write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files], cache_root=tmp_path / ".cache")
    finally:
        os.chdir(old)
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    return calls, r


def _find(r, label, id_contains):
    return next(n["id"] for n in r["nodes"]
                if n["label"] == label and id_contains in n["id"])


_LIB = (
    "namespace Demo\n{\n"
    "    public interface IReport { string Build(string name); }\n"
    "    public class Report : IReport { public string Build(string name) => name; }\n"
    "    public class Widget { public void Spin() { } }\n"
    "    public class Item { }\n"
    "    public class List<T> { public void Add(T item) { } }\n"
    "    public class Box<T> { public T Value() => default; }\n"
    "    public static class ServiceFactory\n    {\n"
    "        public static T Get<T>(object scope) where T : new() => new T();\n"
    "        public static Widget Make() => new Widget();\n"
    "        public static List<T> CreateList<T>() => new List<T>();\n"
    "        public static Widget Pick(int a) => null;\n"
    "        public static IReport Pick(string b) => null;\n"
    "        public static T Infer<T>(T value) => value;\n"
    "    }\n"
    "}\n"
)


def _consumer(body: str) -> str:
    return (
        "namespace Demo\n{\n"
        f"    public class Consumer {{ public void Run(object scope) {{ {body} }} }}\n"
        "}\n"
    )


def _run(r):
    return _find(r, ".Run()", "consumer")


def test_generic_factory_same_file(tmp_path):
    calls, r = _calls(tmp_path, {
        "All.cs": _LIB + _consumer(
            "var report = ServiceFactory.Get<IReport>(scope); report.Build(\"daily\");"
        ),
    })
    assert (_run(r), _find(r, ".Build()", "ireport")) in calls
    assert (_run(r), _find(r, ".Build()", "_report_")) not in calls


def test_generic_factory_cross_file(tmp_path):
    calls, r = _calls(tmp_path, {
        "Lib.cs": _LIB,
        "Consumer.cs": _consumer(
            "var report = ServiceFactory.Get<IReport>(scope); report.Build(\"daily\");"
        ),
    })
    assert (_run(r), _find(r, ".Build()", "ireport")) in calls


def test_non_generic_return_type(tmp_path):
    calls, r = _calls(tmp_path, {
        "Lib.cs": _LIB,
        "Consumer.cs": _consumer("var w = ServiceFactory.Make(); w.Spin();"),
    })
    assert (_run(r), _find(r, ".Spin()", "widget")) in calls


def test_generic_list_return_type(tmp_path):
    calls, r = _calls(tmp_path, {
        "Lib.cs": _LIB,
        "Consumer.cs": _consumer(
            "var items = ServiceFactory.CreateList<Item>(); items.Add(null);"
        ),
    })
    assert (_run(r), _find(r, ".Add()", "list")) in calls


def test_ambiguous_overload_no_edge(tmp_path):
    calls, r = _calls(tmp_path, {
        "Lib.cs": _LIB,
        "Consumer.cs": _consumer("var w = ServiceFactory.Pick(1); w.Spin();"),
    })
    assert (_run(r), _find(r, ".Spin()", "widget")) not in calls


def test_missing_declaration_no_edge(tmp_path):
    calls, r = _calls(tmp_path, {
        "Lib.cs": _LIB,
        "Consumer.cs": _consumer(
            "var w = ServiceFactory.Unknown<Widget>(); w.Spin();"
            " var v = Elsewhere.Get<Widget>(scope); v.Spin();"
        ),
    })
    assert (_run(r), _find(r, ".Spin()", "widget")) not in calls


def test_inferred_generic_no_edge(tmp_path):
    calls, r = _calls(tmp_path, {
        "Lib.cs": _LIB,
        "Consumer.cs": _consumer(
            "var w = ServiceFactory.Infer(new Widget()); w.Spin();"
        ),
    })
    assert (_run(r), _find(r, ".Spin()", "widget")) not in calls


def test_class_type_parameter_return_no_edge(tmp_path):
    calls, r = _calls(tmp_path, {
        "Lib.cs": _LIB,
        "Consumer.cs": _consumer(
            "var box = new Box<Widget>(); var w = box.Value(); w.Spin();"
        ),
    })
    assert (_run(r), _find(r, ".Value()", "box")) in calls
    assert (_run(r), _find(r, ".Spin()", "widget")) not in calls


def test_explicit_type_and_new_still_resolve(tmp_path):
    calls, r = _calls(tmp_path, {
        "Lib.cs": _LIB,
        "Consumer.cs": _consumer(
            "IReport a = ServiceFactory.Get<IReport>(scope); a.Build(\"x\");"
            " var w = new Widget(); w.Spin();"
        ),
    })
    assert (_run(r), _find(r, ".Build()", "ireport")) in calls
    assert (_run(r), _find(r, ".Spin()", "widget")) in calls
