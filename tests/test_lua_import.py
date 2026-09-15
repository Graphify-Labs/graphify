from pathlib import Path

from graphify.build import build_from_json
from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _import_edges(result: dict) -> set[tuple[str, str, str]]:
    return {
        (edge["source"], edge["target"], edge["relation"])
        for edge in result["edges"]
        if edge["relation"] == "imports"
    }


def test_lua_bare_require_emits_import_edge(tmp_path):
    """A bare `require("mod")` statement (no assignment) is the common
    Neovim-config idiom and must produce the same `imports` edge as the
    assigned form (#3320)."""
    _write(tmp_path / "init.lua", 'require("config.lazy")\n')
    _write(tmp_path / "config.lazy.lua", "-- lazy\n")

    result = extract(
        [tmp_path / "init.lua", tmp_path / "config.lazy.lua"],
        root=tmp_path,
        cache_root=tmp_path,
        parallel=False,
    )

    assert ("init", "config_lazy", "imports") in _import_edges(result)


def test_lua_assigned_require_still_emits_import_edge(tmp_path):
    """Positive control: `local x = require("mod")` must keep working exactly
    as it did before (#3320)."""
    _write(tmp_path / "init.lua", 'local ok = require("config.lazy")\n')
    _write(tmp_path / "config.lazy.lua", "-- lazy\n")

    result = extract(
        [tmp_path / "init.lua", tmp_path / "config.lazy.lua"],
        root=tmp_path,
        cache_root=tmp_path,
        parallel=False,
    )

    assert ("init", "config_lazy", "imports") in _import_edges(result)


def test_lua_multiple_bare_requires_each_emit_an_import_edge(tmp_path):
    """The realistic Neovim `init.lua` shape: several bare requires, one per
    line, each need their own `imports` edge (#3320)."""
    _write(
        tmp_path / "init.lua",
        'require("config.options")\nrequire("config.keymaps")\n',
    )
    _write(tmp_path / "config.options.lua", "-- options\n")
    _write(tmp_path / "config.keymaps.lua", "-- keymaps\n")

    result = extract(
        [
            tmp_path / "init.lua",
            tmp_path / "config.options.lua",
            tmp_path / "config.keymaps.lua",
        ],
        root=tmp_path,
        cache_root=tmp_path,
        parallel=False,
    )

    edges = _import_edges(result)
    assert ("init", "config_options", "imports") in edges
    assert ("init", "config_keymaps", "imports") in edges


def test_lua_bare_require_resolves_lua_directory_layout(tmp_path):
    """The standard `lua/config/lazy.lua` layout, not just the flattened
    filename from the original repro, must resolve for a bare require — and
    resolve to the real `lua/config/lazy.lua` node, not just to some
    `imports` edge with any target (#3320)."""
    _write(tmp_path / "init.lua", 'require("config.lazy")\n')
    _write(tmp_path / "lua" / "config" / "lazy.lua", "-- lazy\n")

    result = extract(
        [tmp_path / "init.lua", tmp_path / "lua" / "config" / "lazy.lua"],
        root=tmp_path,
        cache_root=tmp_path,
        parallel=False,
    )

    graph = build_from_json(result)
    assert graph.has_edge("init", "lua_config_lazy")
    assert graph["init"]["lua_config_lazy"]["relation"] == "imports"


def test_lua_bare_require_without_parens_single_quotes(tmp_path):
    """`require 'mod'` (no parens) is valid Lua and must be treated the same
    as the parenthesized bare form (#3320)."""
    _write(tmp_path / "init.lua", "require 'config.lazy'\n")
    _write(tmp_path / "config.lazy.lua", "-- lazy\n")

    result = extract(
        [tmp_path / "init.lua", tmp_path / "config.lazy.lua"],
        root=tmp_path,
        cache_root=tmp_path,
        parallel=False,
    )

    assert ("init", "config_lazy", "imports") in _import_edges(result)


def test_lua_non_require_call_still_recurses_into_its_callback(tmp_path):
    """A plain (non-`require`) Lua call must still be walked into: a
    `local function` declared inside a callback passed to it (the
    `vim.keymap.set`/`vim.defer_fn` idiom) must still be discovered. The
    bare-require fix must not treat every Lua call like a require and skip
    its children (#3320)."""
    _write(
        tmp_path / "init.lua",
        'vim.keymap.set("n", "x", function()\n'
        "  local function inner() end\n"
        "end)\n",
    )

    result = extract([tmp_path / "init.lua"], root=tmp_path, cache_root=tmp_path, parallel=False)

    node_ids = {node["id"] for node in result["nodes"]}
    assert "init_inner" in node_ids
    contains_edges = {
        (edge["source"], edge["target"])
        for edge in result["edges"]
        if edge["relation"] == "contains"
    }
    assert ("init", "init_inner") in contains_edges


def test_lua_method_style_require_is_not_an_import(tmp_path):
    """`foo.require("mod")` / `bar:require("mod")` call something named
    `require` on a table/object, not the global `require` builtin — the
    bare-call check must not mistake a method-style call for a real
    module import (#3320)."""
    _write(tmp_path / "mod.lua", "-- mod\n")
    _write(tmp_path / "init.lua", 'foo.require("mod")\nbar:require("mod")\n')

    result = extract(
        [tmp_path / "init.lua", tmp_path / "mod.lua"],
        root=tmp_path,
        cache_root=tmp_path,
        parallel=False,
    )

    assert not _import_edges(result)


def test_lua_bare_require_without_parens_double_quotes(tmp_path):
    """`require "mod"` (no parens, double quotes) is valid Lua and must be
    treated the same as the parenthesized bare form (#3320)."""
    _write(tmp_path / "init.lua", 'require "config.lazy"\n')
    _write(tmp_path / "config.lazy.lua", "-- lazy\n")

    result = extract(
        [tmp_path / "init.lua", tmp_path / "config.lazy.lua"],
        root=tmp_path,
        cache_root=tmp_path,
        parallel=False,
    )

    assert ("init", "config_lazy", "imports") in _import_edges(result)
