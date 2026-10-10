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

import json
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


def test_same_file_module_reference_does_not_clobber_contains(tmp_path: Path):
    """A module aliasing another module declared in the SAME file must be left
    unresolved. The alias `imports` edge's source is the FILE node, which
    already `contains` that module, so retargeting it would duplicate the
    file->module pair with a weaker relation and -- in the non-multi build
    graph, where `imports` and `contains` are both specific relations -- clobber
    the structural `contains` edge (#3603 follow-up guard). Cross-file
    resolution is covered by the repro test above; here the same-file case must
    fail closed."""
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
    contains = {
        (e["source"], e["target"])
        for e in result["edges"]
        if e["relation"] == "contains"
    }
    resolved_imports = {
        (e["source"], e["target"])
        for e in result["edges"]
        if e["relation"] == "imports"
    }
    # The structural containment edge is intact ...
    assert (demo_file, inner) in contains
    # ... and the same-file alias was NOT retargeted onto Inner's node (which
    # would duplicate that pair as a weaker `imports` and clobber `contains`).
    assert (demo_file, inner) not in resolved_imports


def test_ambiguous_module_name_across_files_yields_no_resolution(tmp_path: Path):
    """Two DIFFERENT files each declare a module with the same bare name --
    the exactly-one-candidate guard must leave the reference exactly as
    extracted rather than guessing which one the caller meant."""
    result = _extract(tmp_path, {
        "a/dup.ex": (
            "defmodule Demo.Dup do\n"
            "  def f, do: 1\n"
            "end\n"
        ),
        "b/dup.ex": (
            "defmodule Demo.Dup do\n"
            "  def g, do: 2\n"
            "end\n"
        ),
        "caller.ex": (
            "defmodule Demo.Caller do\n"
            "  alias Demo.Dup\n"
            "\n"
            "  def run, do: Dup.f()\n"
            "end\n"
        ),
    })
    caller_file = _find_file(result, "caller.ex")
    node_ids = {n["id"] for n in result["nodes"]}
    import_targets = {
        e["target"] for e in result["edges"]
        if e["relation"] == "imports" and e["source"] == caller_file
    }
    assert import_targets, "the alias edge must still exist"
    assert not (import_targets & node_ids), \
        "an ambiguous module name must not resolve to either same-named definition"


def test_genuinely_external_module_stays_unresolved(tmp_path: Path):
    """A module with no matching definition anywhere in the corpus (stdlib,
    a hex dependency) must be left as an external reference, not fabricated."""
    result = _extract(tmp_path, {
        "caller.ex": (
            "defmodule Demo.Caller do\n"
            "  alias Logger\n"
            "\n"
            "  def run, do: Logger.info(\"hi\")\n"
            "end\n"
        ),
    })
    caller_file = _find_file(result, "caller.ex")
    node_ids = {n["id"] for n in result["nodes"]}
    import_targets = {
        e["target"] for e in result["edges"]
        if e["relation"] == "imports" and e["source"] == caller_file
    }
    assert import_targets
    assert not (import_targets & node_ids)


def test_nested_module_does_not_capture_foreign_use(tmp_path: Path):
    """A nested `defmodule` is labeled with its bare inner name, so an unrelated
    `use <Name>` / `alias <Name>` from another file must NOT latch onto it
    (#3603 follow-up guard). Only top-level modules are indexed as targets."""
    result = _extract(tmp_path, {
        "lib/app/application.ex": (
            "defmodule MyApp.Application do\n"
            "  defmodule Supervisor do\n"
            "    def child_spec(_), do: %{}\n"
            "  end\n"
            "end\n"
        ),
        "lib/app/worker.ex": (
            "defmodule MyApp.Worker do\n"
            "  use Supervisor\n"
            "end\n"
        ),
    })
    nested = _find(result, "Supervisor")
    resolved_targets = {
        e["target"] for e in result["edges"] if e["relation"] == "imports"
    }
    # The `use Supervisor` in worker.ex must not resolve onto the nested module
    # (it means the stdlib/behaviour Supervisor, which is genuinely external).
    assert nested not in resolved_targets


def test_resolution_survives_incremental_rebuild(tmp_path: Path):
    """The cross-file alias must stay resolved on the real `graphify update` /
    watch path, where the unchanged target module arrives as a resolution-context
    node. This only holds if the `_elixir_module` marker rides through the
    context builder's allow-list -- the exact path #3566's own test bypassed."""
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "accounts.ex").write_text(
        "defmodule Demo.Accounts do\n  def list_users, do: []\nend\n", encoding="utf-8"
    )
    caller = corpus / "web.ex"

    def _caller(extra: str = "") -> str:
        body = "  def index, do: Accounts.list_users()\n" + extra
        return f"defmodule Demo.Web do\n  alias Demo.Accounts\n{body}end\n"

    caller.write_text(_caller(), encoding="utf-8")
    graph_path = corpus / "graphify-out" / "graph.json"

    def resolves() -> bool:
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        accounts = next(
            (n["id"] for n in data["nodes"] if n.get("label") == "Demo.Accounts"), None
        )
        if accounts is None:
            return False
        return any(
            e.get("relation") == "imports" and e.get("target") == accounts
            for e in data["links"]
        )

    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    assert resolves(), "full build resolves the cross-file alias"

    # Change ONLY the caller: accounts.ex is unchanged, so its top-level module
    # node is fed back as a resolution-context node. The alias must still resolve.
    caller.write_text(_caller("  def dup, do: Accounts.list_users()\n"), encoding="utf-8")
    assert _rebuild_code(corpus, changed_paths=[caller], no_cluster=True,
                         acquire_lock=False) is True
    assert resolves(), "alias stays resolved after an incremental rebuild"
