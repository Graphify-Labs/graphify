from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _call_edges(path: Path, base: Path) -> set[tuple[str, str]]:
    result = extract([path], root=base, cache_root=base, parallel=False)
    label = {node["id"]: node["label"] for node in result["nodes"]}
    return {
        (label.get(edge["source"], edge["source"]), label.get(edge["target"], edge["target"]))
        for edge in result["edges"]
        if edge["relation"] in ("calls", "indirect_call")
    }


def test_lua_self_colon_call_resolves_to_sibling_method(tmp_path):
    """`self:other()` inside a colon method is sugar for a call to a sibling
    method on the same table. The receiver `self` is untyped on its own, but the
    enclosing method's table (`Animal`) is known, so the call must resolve to
    `Animal:describe`. Before the fix the colon call was dropped entirely: the
    `method_index_expression` callee lives in the `method` field, but the Lua
    config read the (absent) `name` field, so no call edge was emitted (#3991)."""
    src = _write(
        tmp_path / "animal.lua",
        "local Animal = {}\n"
        "function Animal:speak()\n"
        "    return self:describe()\n"
        "end\n"
        "function Animal:describe()\n"
        "    return self.name\n"
        "end\n",
    )
    assert ("Animal:speak()", "Animal:describe()") in _call_edges(src, tmp_path)


def test_lua_self_colon_call_resolves_dot_defined_sibling(tmp_path):
    """A sibling declared with dot syntax (`function Animal.helper()`) is the
    same method; `self:helper()` must still resolve to it (#3991)."""
    src = _write(
        tmp_path / "animal.lua",
        "local Animal = {}\n"
        "function Animal.helper()\n"
        "    return 1\n"
        "end\n"
        "function Animal:run()\n"
        "    return self:helper()\n"
        "end\n",
    )
    assert ("Animal:run()", "Animal.helper()") in _call_edges(src, tmp_path)


def test_lua_self_colon_call_does_not_bind_to_unrelated_bare_function(tmp_path):
    """Fail-closed: when the table has no matching sibling, `self:process()` must
    NOT bind to an unrelated top-level function named `process`. Resolution stays
    scoped to the enclosing table (#3991)."""
    src = _write(
        tmp_path / "animal.lua",
        "function process()\n"
        "    return 1\n"
        "end\n"
        "local Animal = {}\n"
        "function Animal:run()\n"
        "    return self:process()\n"
        "end\n",
    )
    assert ("Animal:run()", "process()") not in _call_edges(src, tmp_path)


def test_lua_colon_call_on_unknown_receiver_is_fail_closed(tmp_path):
    """A colon call on an arbitrary receiver (`obj:process()`) has an unknown
    type, so it must NOT bind by bare name to an unrelated top-level
    `process` — only the literal `self` receiver is resolved (#3991)."""
    src = _write(
        tmp_path / "animal.lua",
        "function process()\n"
        "    return 1\n"
        "end\n"
        "local Animal = {}\n"
        "function Animal:run()\n"
        "    local obj = make()\n"
        "    return obj:process()\n"
        "end\n",
    )
    assert ("Animal:run()", "process()") not in _call_edges(src, tmp_path)


def test_lua_dot_and_plain_calls_still_resolve(tmp_path):
    """Positive control: the dot-call (`M.helper()`) and plain-call (`helper()`)
    paths that already worked must keep working (#3991)."""
    src = _write(
        tmp_path / "mod.lua",
        "local M = {}\n"
        "function M.helper()\n"
        "    return 1\n"
        "end\n"
        "function M.main()\n"
        "    return M.helper()\n"
        "end\n",
    )
    assert ("M.main()", "M.helper()") in _call_edges(src, tmp_path)
