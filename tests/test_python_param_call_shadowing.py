"""A call through an enclosing function's parameter has no known target (#5418)."""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.extract import extract, extract_python

HANDLER = "def handler():\n    return 'module'\n\n"


def _calls(tmp_path: Path, body: str) -> set[tuple[str, str]]:
    """(caller label, target id tail) for every `calls` edge in one file."""
    path = tmp_path / "probe.py"
    path.write_text(HANDLER + body, encoding="utf-8")
    result = extract_python(path)
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    return {
        (labels[e["source"]], e["target"].split("probe_", 1)[1])
        for e in result["edges"] if e["relation"] == "calls"
    }


# 1. The bug: none of these may link to the module function.
@pytest.mark.parametrize("body", [
    pytest.param("def factory(handler):\n    return lambda cb=handler(): cb\n", id="lambda-default"),
    pytest.param(
        "def outer(handler):\n    def inner():\n        return lambda cb=handler(): cb\n"
        "    return inner\n", id="captured-lambda-default"),
    pytest.param("def plain(handler):\n    return handler()\n", id="direct"),
    pytest.param("def kwonly(*, handler=None):\n    return handler()\n", id="keyword-only"),
    pytest.param(
        "def outer(handler):\n    class C:\n        def run(self):\n"
        "            return handler()\n    return C\n", id="captured-by-method"),
    pytest.param(
        "def outer(handler):\n    class C:\n        def handler(self):\n            pass\n"
        "        def run(self):\n            return handler()\n    return C\n",
        id="class-scope-invisible-to-method"),
])
def test_call_through_parameter_is_not_linked(tmp_path, body):
    assert _calls(tmp_path, body) == set()


# 2. Guard against over-blocking: real targets keep their edge.
@pytest.mark.parametrize("body, expected", [
    pytest.param(
        "def real():\n    return lambda cb=handler(): cb\n",
        {("real()", "handler")}, id="unshadowed"),
    pytest.param(
        "def outer(handler):\n    def handler():\n        pass\n"
        "    return lambda cb=handler(): cb\n",
        {("outer()", "outer_handler")}, id="local-def-rebinds"),
    pytest.param(
        "def outer(handler):\n    def mid():\n        def handler():\n            pass\n"
        "        return lambda cb=handler(): cb\n    return mid\n",
        {("mid()", "outer_mid_handler")}, id="nearer-def-wins"),
    pytest.param(
        "def outer(handler):\n    def inner():\n        global handler\n"
        "        return handler()\n    return inner\n",
        {("inner()", "handler")}, id="global"),
    pytest.param(
        "def outer(cb=handler()):\n    def inner(handler):\n        pass\n"
        "    return handler()\n",
        {("outer()", "handler")}, id="sibling-scope-parameter"),
])
def test_call_that_does_not_read_the_parameter_keeps_its_edge(tmp_path, body, expected):
    assert _calls(tmp_path, body) == expected


# 3. Dropping the callee must not drop calls inside its arguments.
def test_arguments_of_a_parameter_call_are_still_visited(tmp_path):
    body = "def real():\n    pass\n\ndef run(handler):\n    return handler(real())\n"
    assert _calls(tmp_path, body) == {("run()", "real")}


# 4. The second pass (resolution.py): imported name hidden by a parameter.
def test_captured_parameter_does_not_link_across_files(tmp_path):
    (tmp_path / "lib.py").write_text(HANDLER, encoding="utf-8")
    (tmp_path / "user.py").write_text(
        "from lib import handler\n\n"
        "def outer(handler):\n    def inner():\n"
        "        return lambda cb=handler(): cb\n    return inner\n\n"
        "def real():\n    return lambda cb=handler(): cb\n",
        encoding="utf-8",
    )
    result = extract(
        sorted(tmp_path.glob("*.py")), cache_root=tmp_path, parallel=False)
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    assert {
        (labels[e["source"]], labels[e["target"]])
        for e in result["edges"] if e["relation"] == "calls"
    } == {("real()", "handler()")}


# 5. An explicit import nearer than the parameter still wins.
def test_local_import_over_parameter_keeps_its_edge(tmp_path):
    (tmp_path / "lib.py").write_text(HANDLER, encoding="utf-8")
    (tmp_path / "user.py").write_text(
        "def outer(handler):\n    def inner():\n        from lib import handler\n"
        "        return handler()\n    return inner\n",
        encoding="utf-8",
    )
    result = extract(
        sorted(tmp_path.glob("*.py")), cache_root=tmp_path, parallel=False)
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    # The import pass also credits outer() with inner()'s call; not asserted here.
    assert ("inner()", "handler()") in {
        (labels[e["source"]], labels[e["target"]])
        for e in result["edges"] if e["relation"] == "calls"
    }
