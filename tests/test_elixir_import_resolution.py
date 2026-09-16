"""Elixir cross-file alias/import/require/use resolution (#2556).

`extract_elixir` mints a module's own node id with the defining file's stem
(`_make_id(stem, module_name)`) but an alias/import/require/use target with
just the bare module name (`_make_id(module_name)`) -- the two can only
match when a module refers to itself, so a reference to a module declared
in ANY other file was silently dropped as dangling at build time. On a real
900-file Elixir/Phoenix project this discarded 13% of extracted edges --
the entire internal module dependency graph.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path: Path, files: dict[str, str]):
    paths = []
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    return extract(paths, cache_root=tmp_path / "graphify-out")


def _find(result: dict, label: str, id_contains: str = "") -> str:
    return next(
        node["id"]
        for node in result["nodes"]
        if node.get("label") == label and id_contains in node["id"]
    )


def _find_file(result: dict, filename: str) -> str:
    """An `imports` edge's source is the FILE node (extract_elixir emits it
    at file scope), not the module node the file happens to declare."""
    return next(
        node["id"]
        for node in result["nodes"]
        if node.get("label") == filename
    )


_REPRO_CORPUS = {
    "lib/demo/accounts.ex": (
        "defmodule Demo.Accounts do\n"
        "  def list_users, do: []\n"
        "end\n"
    ),
    "lib/demo/web.ex": (
        "defmodule Demo.Web do\n"
        "  alias Demo.Accounts\n"
        "\n"
        "  def index, do: Accounts.list_users()\n"
        "end\n"
    ),
}


def test_alias_resolves_to_the_module_declared_in_another_file(tmp_path: Path):
    result = _extract(tmp_path, _REPRO_CORPUS)
    web_file = _find_file(result, "web.ex")
    accounts = _find(result, "Demo.Accounts")
    imports = {
        (e["source"], e["target"])
        for e in result["edges"]
        if e["relation"] == "imports"
    }
    assert (web_file, accounts) in imports
    node_ids = {n["id"] for n in result["nodes"]}
    assert accounts in node_ids, "the import target must be a real, non-dangling node"


def test_same_file_module_reference_is_unaffected(tmp_path: Path):
    """Negative control: a module importing something declared in the SAME
    file already resolved before this fix (both ids share the same stem)
    and must keep working exactly as before."""
    result = _extract(tmp_path, {
        "lib/demo.ex": (
            "defmodule Demo.Inner do\n"
            "  def go, do: 1\n"
            "end\n"
            "\n"
            "defmodule Demo.Outer do\n"
            "  alias Demo.Inner\n"
            "\n"
            "  def run, do: Inner.go()\n"
            "end\n"
        ),
    })
    demo_file = _find_file(result, "demo.ex")
    inner = _find(result, "Demo.Inner")
    imports = {
        (e["source"], e["target"])
        for e in result["edges"]
        if e["relation"] == "imports"
    }
    assert (demo_file, inner) in imports
