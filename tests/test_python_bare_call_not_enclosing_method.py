"""A bare call in a Python method body never resolves to a method.

Python reads a bare name from locals, enclosing functions, module globals, then
builtins; a method is only reachable through self, cls, or the class. The call
walk's file-wide name map also held method names, so `get_build_status(...)`
inside `AsyncTemplate.get_build_status` bound to the method itself (a false
self-recursion) instead of the imported or module-level function it calls.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract

_BUILD_API = "def get_build_status(c, b):\n    return 1\n"


def _calls(tmp_path: Path, files: dict[str, str]) -> set[tuple[str, str]]:
    paths = []
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        paths.append(p)
    r = extract(paths, root=tmp_path, cache_root=tmp_path / "graphify-out", parallel=False)
    nodes = {n["id"]: n for n in r["nodes"]}

    def name(nid: str) -> str:
        return f'{nodes[nid]["label"]}@{nodes[nid].get("source_file")}'

    return {(name(e["source"]), name(e["target"])) for e in r["edges"] if e["relation"] == "calls"}


def test_classmethod_calling_imported_function_of_same_name(tmp_path):
    calls = _calls(tmp_path, {
        "tpl/__init__.py": "",
        "tpl/build_api.py": _BUILD_API,
        "tpl/main.py": (
            "from tpl.build_api import get_build_status\n\n"
            "class AsyncTemplate:\n"
            "    @classmethod\n"
            "    def get_build_status(cls, b):\n"
            "        return get_build_status(None, b)\n"
        ),
    })
    assert calls == {(".get_build_status()@tpl/main.py", "get_build_status()@tpl/build_api.py")}


def test_plain_method_calling_imported_function_of_same_name(tmp_path):
    calls = _calls(tmp_path, {
        "tpl/__init__.py": "",
        "tpl/build_api.py": _BUILD_API,
        "tpl/main.py": (
            "from tpl.build_api import get_build_status\n\n"
            "class Template:\n"
            "    def get_build_status(self, b):\n"
            "        return get_build_status(None, b)\n"
        ),
    })
    assert calls == {(".get_build_status()@tpl/main.py", "get_build_status()@tpl/build_api.py")}


def test_method_calling_same_file_module_function_of_same_name(tmp_path):
    calls = _calls(tmp_path, {
        "m.py": (
            "def helper():\n    return 1\n\n"
            "class C:\n"
            "    def helper(self):\n"
            "        return helper()\n"
        ),
    })
    assert calls == {(".helper()@m.py", "helper()@m.py")}


def test_nested_function_in_method_skips_the_method(tmp_path):
    calls = _calls(tmp_path, {
        "m.py": (
            "def helper():\n    return 1\n\n"
            "class C:\n"
            "    def helper(self):\n"
            "        def inner():\n"
            "            return helper()\n"
            "        return inner()\n"
        ),
    })
    assert ("inner()@m.py", "helper()@m.py") in calls
    assert ("inner()@m.py", ".helper()@m.py") not in calls


def test_module_function_recursion_still_links_to_itself(tmp_path):
    calls = _calls(tmp_path, {
        "m.py": "def fact(n):\n    return 1 if n < 2 else n * fact(n - 1)\n",
    })
    assert calls == {("fact()@m.py", "fact()@m.py")}


def test_self_method_call_still_resolves(tmp_path):
    calls = _calls(tmp_path, {
        "m.py": (
            "class C:\n"
            "    def a(self):\n        return self.b()\n"
            "    def b(self):\n        return 1\n"
        ),
    })
    assert calls == {(".a()@m.py", ".b()@m.py")}
