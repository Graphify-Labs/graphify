"""Lua `require(...)` import resolution.

A bare `require("mod")` statement with no assignment — the common Neovim/LazyVim
config idiom (`require("config.lazy")` in `init.lua`) — must resolve to an
`imports` edge just like the assigned `local x = require("mod")` form (#3320).
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _import_edges(result: dict) -> list[dict]:
    return [e for e in result["edges"] if e["relation"] == "imports"]


def test_bare_require_statement_emits_import_edge(tmp_path: Path):
    source = _write(tmp_path / "init.lua", 'require("config.lazy")\n')
    target = _write(tmp_path / "config.lazy.lua", "-- lazy config\n")

    result = extract([source, target], cache_root=tmp_path)

    imports = _import_edges(result)
    assert len(imports) == 1
    assert imports[0]["source"] == "init"
    assert imports[0]["target"] == "config_lazy"


def test_multiple_bare_requires_each_emit_an_edge(tmp_path: Path):
    source = _write(
        tmp_path / "init.lua",
        'require("config.lazy")\nrequire("config.options")\n',
    )
    _write(tmp_path / "config.lazy.lua", "-- lazy\n")
    _write(tmp_path / "config.options.lua", "-- options\n")

    result = extract([source, tmp_path / "config.lazy.lua", tmp_path / "config.options.lua"], cache_root=tmp_path)

    targets = sorted(e["target"] for e in _import_edges(result))
    assert targets == ["config_lazy", "config_options"]


def test_similarly_named_call_does_not_emit_import(tmp_path: Path):
    """A helper whose name merely ends in ``require`` (or a string literal that
    contains ``require(...)``) must not be mistaken for a real ``require`` import."""
    source = _write(
        tmp_path / "init.lua",
        'myrequire("config.lazy")\nprint("require(\\"config.lazy\\")")\n',
    )
    _write(tmp_path / "config.lazy.lua", "-- lazy config\n")

    result = extract([source, tmp_path / "config.lazy.lua"], cache_root=tmp_path)

    assert _import_edges(result) == []


def test_assigned_require_still_emits_exactly_one_edge(tmp_path: Path):
    """Guard against a duplicate edge: the assigned form is a
    ``variable_declaration`` whose nested ``function_call`` must not be
    re-dispatched to the import handler."""
    source = _write(tmp_path / "init.lua", 'local ok = require("config.lazy")\n')
    _write(tmp_path / "config.lazy.lua", "-- lazy config\n")

    result = extract([source, tmp_path / "config.lazy.lua"], cache_root=tmp_path)

    imports = _import_edges(result)
    assert len(imports) == 1
    assert imports[0]["source"] == "init"
    assert imports[0]["target"] == "config_lazy"
