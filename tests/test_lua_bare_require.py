"""Regression tests for bare Lua `require("m")` statements (#3320).

`_import_lua` only ran for `variable_declaration` nodes, so an import edge came
out of `local x = require("m")` but not out of the far more common Neovim idiom
— a `require("m")` statement with no assignment, which tree-sitter-lua parses as
a plain `function_call`. Every `init.lua` written as a list of bare requires
therefore produced zero import edges. The fix routes those call nodes through
the same handler via `import_call_types`, which (unlike `import_types`) does not
stop the walk, so Lua call extraction is unaffected.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _import_targets(result: dict, source: str) -> list[str]:
    return [
        edge["target"]
        for edge in result["edges"]
        if edge["relation"] == "imports" and edge["source"] == source
    ]


def test_bare_require_emits_import_edge(tmp_path: Path):
    entry = _write(tmp_path / "init.lua", 'require("lazy")\n')
    module = _write(tmp_path / "lazy.lua", "local M = {}\nreturn M\n")

    result = extract([entry, module], cache_root=tmp_path)

    assert _import_targets(result, "init") == ["lazy"]


def test_bare_require_matches_the_assigned_form(tmp_path: Path):
    """The two spellings of the same dependency must produce the same edge."""
    module = _write(tmp_path / "lazy.lua", "local M = {}\nreturn M\n")
    bare = _write(tmp_path / "bare.lua", 'require("lazy")\n')
    assigned = _write(tmp_path / "assigned.lua", 'local ok = require("lazy")\n')

    result = extract([module, bare, assigned], cache_root=tmp_path)

    assert _import_targets(result, "bare") == _import_targets(result, "assigned")


def test_bare_require_without_parentheses(tmp_path: Path):
    entry = _write(tmp_path / "init.lua", 'require "lazy"\n')
    module = _write(tmp_path / "lazy.lua", "local M = {}\nreturn M\n")

    result = extract([entry, module], cache_root=tmp_path)

    assert _import_targets(result, "init") == ["lazy"]


def test_every_bare_require_in_a_list_is_reported(tmp_path: Path):
    entry = _write(
        tmp_path / "init.lua",
        'require("options")\nrequire("keymaps")\nrequire("plugins")\n',
    )
    modules = [
        _write(tmp_path / f"{name}.lua", "-- module\n")
        for name in ("options", "keymaps", "plugins")
    ]

    result = extract([entry, *modules], cache_root=tmp_path)

    assert _import_targets(result, "init") == ["options", "keymaps", "plugins"]


def test_lazy_require_inside_a_function_body(tmp_path: Path):
    """A require at any lexical depth is still a dependency of the file."""
    entry = _write(
        tmp_path / "init.lua",
        "function setup()\n  require(\"lazy\")\nend\n",
    )
    module = _write(tmp_path / "lazy.lua", "-- module\n")

    result = extract([entry, module], cache_root=tmp_path)

    assert _import_targets(result, "init") == ["lazy"]


def test_a_non_require_call_produces_no_import_edge(tmp_path: Path):
    entry = _write(tmp_path / "init.lua", "local M = {}\nfunction M.go() end\nM.go()\n")

    result = extract([entry], cache_root=tmp_path)

    assert _import_targets(result, "init") == []


def test_bare_require_does_not_suppress_call_extraction(tmp_path: Path):
    """`import_call_types` must not swallow the call node the way imports do."""
    entry = _write(
        tmp_path / "init.lua",
        'require("lazy")\n'
        "function helper() end\n"
        "function setup()\n  helper()\nend\n",
    )
    module = _write(tmp_path / "lazy.lua", "-- module\n")

    result = extract([entry, module], cache_root=tmp_path)

    calls = {
        (edge["source"], edge["target"])
        for edge in result["edges"]
        if edge["relation"] == "calls"
    }
    assert ("init_setup", "init_helper") in calls
    assert _import_targets(result, "init") == ["lazy"]


def test_bare_require_is_reported_once(tmp_path: Path):
    """The module-level walk and the call walk must not both emit the edge."""
    entry = _write(tmp_path / "init.lua", 'require("lazy")\n')
    module = _write(tmp_path / "lazy.lua", "-- module\n")

    result = extract([entry, module], cache_root=tmp_path)

    assert len(_import_targets(result, "init")) == 1
