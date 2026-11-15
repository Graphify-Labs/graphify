"""Unqualified Elixir calls resolve only into imported/used modules (#4001).

The shared cross-file call pass bound a bare call to any same-named def in the
corpus. In Elixir an unqualified call can only reach the caller's own module,
Kernel, or a module the file `import`s or `use`s, so every migration's
`table(:users)` (Ecto.Migration, pulled in by `use`) landed on an unrelated
Phoenix component's `table/1` and turned it into the top god node.
"""
from __future__ import annotations

import json
from pathlib import Path

from graphify.extract import extract

_COMPONENTS = (
    "defmodule MyAppWeb.CoreComponents do\n"
    "  def table(assigns), do: assigns\n"
    "end\n"
)
_HELPERS = (
    "defmodule MyApp.Helpers do\n"
    "  def fmt(x), do: x\n"
    "end\n"
)


def _cross_file_calls(tmp_path: Path, files: dict[str, str]) -> set[tuple[str, str]]:
    paths = []
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    result = extract(paths, cache_root=tmp_path / "graphify-out")
    label = {n["id"]: n["label"] for n in result["nodes"]}
    return {
        (label[e["source"]], label[e["target"]])
        for e in result["edges"]
        if e["relation"] == "calls" and e["source"] in label and e["target"] in label
    }


def test_dsl_call_does_not_bind_to_an_unrelated_same_named_def(tmp_path: Path):
    calls = _cross_file_calls(tmp_path, {
        "lib/my_app_web/components/core_components.ex": _COMPONENTS,
        "priv/repo/migrations/20240101000000_create_users.exs": (
            "defmodule MyApp.Repo.Migrations.CreateUsers do\n"
            "  use Ecto.Migration\n"
            "\n"
            "  def change do\n"
            "    create table(:users) do\n"
            "      add :name, :string\n"
            "    end\n"
            "  end\n"
            "end\n"
        ),
    })
    assert ("change()", "table()") not in calls


def test_call_without_import_or_use_does_not_bind(tmp_path: Path):
    calls = _cross_file_calls(tmp_path, {
        "lib/my_app/helpers.ex": _HELPERS,
        # `alias` only shortens the module name; `fmt` is still not in scope.
        "lib/my_app/other.ex": (
            "defmodule MyApp.Other do\n"
            "  alias MyApp.Helpers\n"
            "\n"
            "  def go(x) do\n"
            "    fmt(x)\n"
            "  end\n"
            "end\n"
        ),
    })
    assert ("go()", "fmt()") not in calls


def test_imported_and_used_module_calls_still_resolve(tmp_path: Path):
    calls = _cross_file_calls(tmp_path, {
        "lib/my_app/helpers.ex": _HELPERS,
        "lib/my_app/user.ex": (
            "defmodule MyApp.User do\n"
            "  import MyApp.Helpers\n"
            "\n"
            "  def show(x) do\n"
            "    fmt(x)\n"
            "  end\n"
            "end\n"
        ),
        "lib/my_app/schema.ex": (
            "defmodule MyApp.Schema do\n"
            "  def timestamps_opts, do: []\n"
            "end\n"
        ),
        "lib/my_app/post.ex": (
            "defmodule MyApp.Post do\n"
            "  use MyApp.Schema\n"
            "\n"
            "  def opts do\n"
            "    timestamps_opts()\n"
            "  end\n"
            "end\n"
        ),
    })
    assert ("show()", "fmt()") in calls
    assert ("opts()", "timestamps_opts()") in calls


def test_import_is_scoped_to_the_module_that_declares_it(tmp_path: Path):
    """An `import` applies to the module body it appears in and to modules
    nested in it, not to a sibling module that happens to share the file."""
    calls = _cross_file_calls(tmp_path, {
        "lib/my_app/helpers.ex": _HELPERS,
        "lib/my_app/pair.ex": (
            "defmodule MyApp.Importer do\n"
            "  import MyApp.Helpers\n"
            "\n"
            "  def show(x) do\n"
            "    fmt(x)\n"
            "  end\n"
            "\n"
            "  defmodule Nested do\n"
            "    def inner(x) do\n"
            "      fmt(x)\n"
            "    end\n"
            "  end\n"
            "end\n"
            "\n"
            "defmodule MyApp.Sibling do\n"
            "  def go(x) do\n"
            "    fmt(x)\n"
            "  end\n"
            "end\n"
        ),
    })
    assert ("show()", "fmt()") in calls
    assert ("inner()", "fmt()") in calls
    assert ("go()", "fmt()") not in calls


def test_same_file_sibling_module_does_not_steal_a_bare_call(tmp_path: Path):
    """Two modules in one file each define a same-named function. A bare call
    inside one module must bind to its own def, never to the unrelated
    sibling's -- the in-file resolver built a single flat name -> id table
    that let whichever definition was walked last win, regardless of which
    module the caller actually belonged to.

    Both candidates share the identical label "process()", so a label-pair
    assertion (like the rest of this file uses) cannot tell them apart and
    would pass whichever one wins -- this checks the target node's id
    directly instead, since that is the only thing that actually
    distinguishes ModuleA's def from ModuleB's.
    """
    path = tmp_path / "lib" / "my_app" / "both.ex"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "defmodule MyApp.ModuleA do\n"
        "  def process(x) do\n"
        "    x\n"
        "  end\n"
        "\n"
        "  def go(x) do\n"
        "    process(x)\n"
        "  end\n"
        "end\n"
        "\n"
        "defmodule MyApp.ModuleB do\n"
        "  def process(x) do\n"
        "    x * 2\n"
        "  end\n"
        "end\n"
    )
    result = extract([path], cache_root=tmp_path / "graphify-out")
    go_nid = next(n["id"] for n in result["nodes"] if n["label"] == "go()")
    targets = [
        e["target"] for e in result["edges"]
        if e["source"] == go_nid and e["relation"] == "calls"
    ]
    assert len(targets) == 1, targets
    assert "modulea" in targets[0].lower() and "moduleb" not in targets[0].lower(), (
        f"go() bound to the wrong module's process(): {targets[0]!r}"
    )


def test_same_file_own_module_call_still_resolves(tmp_path: Path):
    """Control: a bare call to a sibling function within the SAME module
    still resolves, with no other same-named def anywhere in the file."""
    calls = _cross_file_calls(tmp_path, {
        "lib/my_app/solo.ex": (
            "defmodule MyApp.Solo do\n"
            "  def helper(x) do\n"
            "    x\n"
            "  end\n"
            "\n"
            "  def run(x) do\n"
            "    helper(x)\n"
            "  end\n"
            "end\n"
        ),
    })
    assert ("run()", "helper()") in calls


def test_imported_call_survives_incremental_rebuild(tmp_path: Path):
    """On `graphify update` the unchanged helpers file arrives only as
    resolution-context nodes; its module must still count as in scope."""
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "helpers.ex").write_text(_HELPERS, encoding="utf-8")
    caller = corpus / "user.ex"

    def _caller(extra: str = "") -> str:
        return (
            "defmodule MyApp.User do\n"
            "  import MyApp.Helpers\n"
            "\n"
            "  def show(x) do\n"
            "    fmt(x)\n"
            "  end\n"
            f"{extra}"
            "end\n"
        )

    caller.write_text(_caller(), encoding="utf-8")
    graph_path = corpus / "graphify-out" / "graph.json"

    def calls() -> set[tuple[str, str]]:
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        label = {n["id"]: n["label"] for n in data["nodes"]}
        return {
            (label[e["source"]], label[e["target"]])
            for e in data["links"]
            if e.get("relation") == "calls" and e["source"] in label and e["target"] in label
        }

    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    assert ("show()", "fmt()") in calls()

    caller.write_text(_caller("\n  def other, do: :ok\n"), encoding="utf-8")
    assert _rebuild_code(corpus, changed_paths=[caller], no_cluster=True,
                         acquire_lock=False) is True
    assert ("show()", "fmt()") in calls()
