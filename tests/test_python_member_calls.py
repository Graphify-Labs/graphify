from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _node_id(result: dict, label: str, source_file: str) -> str:
    matches = [
        node["id"]
        for node in result["nodes"]
        if node.get("label") == label and node.get("source_file") == source_file
    ]
    assert len(matches) == 1, f"expected 1 node {label!r} in {source_file!r}, got {matches}"
    return matches[0]


def _has_edge(result: dict, source: str, target: str, relation: str) -> bool:
    return any(
        edge["source"] == source
        and edge["target"] == target
        and edge["relation"] == relation
        for edge in result["edges"]
    )


def test_python_module_qualified_call_resolves_from_class_method(tmp_path: Path):
    """`module.func()` must resolve to a `calls` edge from a class method too.

    The module-alias arm of `_resolve_python_member_calls()` looked `caller_file`
    up in `file_of_node`, which was populated from `contains` edges only. Methods
    reach their file through `method` (class -> method) instead, so `caller_file`
    was `None` for every method and the arm bailed out: `module.func()` resolved
    from a module-level function but never from a method.
    """
    init = _write(tmp_path / "pkg/__init__.py", "")
    util = _write(tmp_path / "pkg/util.py", "def helper(x):\n    return x + 1\n")
    app = _write(
        tmp_path / "app.py",
        "from pkg import util\n"
        "from pkg.util import helper\n\n\n"
        "class Machine:\n"
        "    def method_qualified(self):\n"
        "        return util.helper(1)\n\n"
        "    def method_bare(self):\n"
        "        return helper(1)\n\n\n"
        "def function_qualified():\n"
        "    return util.helper(1)\n",
    )

    result = extract([init, util, app], cache_root=tmp_path)

    helper = _node_id(result, "helper()", "pkg/util.py")
    method_qualified = _node_id(result, ".method_qualified()", "app.py")
    method_bare = _node_id(result, ".method_bare()", "app.py")
    function_qualified = _node_id(result, "function_qualified()", "app.py")

    # Regression: this is the edge that used to be missing.
    assert _has_edge(result, method_qualified, helper, "calls")

    # Guard rails -- these already worked and must keep working.
    assert _has_edge(result, method_bare, helper, "calls")
    assert _has_edge(result, function_qualified, helper, "calls")
