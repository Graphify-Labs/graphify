"""Qualified Elixir remote calls resolve to the named module (#4206).

`App.Accounts.get_user(id)` and `Accounts.get_user(id)` (after
`alias App.Accounts`) got no `calls` edge, because the extractor kept only the
function name. Worse, `App.Repo.insert(x)` inside a module with its own
`insert/1` was bound to that local function as EXTRACTED.
"""
from __future__ import annotations

import json
from pathlib import Path

from graphify.extract import extract

_ACCOUNTS = (
    "defmodule App.Accounts do\n"
    "  def get_user(id) do\n"
    "    {:user, id}\n"
    "  end\n"
    "end\n"
)
_REPO = (
    "defmodule App.Repo do\n"
    "  def insert(changeset) do\n"
    "    {:ok, changeset}\n"
    "  end\n"
    "end\n"
)


def _qualified(nodes: list[dict], edges: list[dict]) -> dict[tuple[str, str], str]:
    """`calls` edges as (Module.fun, Module.fun) -> confidence."""
    name = {n["id"]: str(n["label"]).removesuffix("()") for n in nodes}
    for e in edges:
        if e["relation"] == "method" and e["source"] in name and e["target"] in name:
            name[e["target"]] = f"{name[e['source']]}.{name[e['target']]}"
    return {
        (name[e["source"]], name[e["target"]]): e["confidence"]
        for e in edges
        if e["relation"] == "calls" and e["source"] in name and e["target"] in name
    }


def _calls(tmp_path: Path, files: dict[str, str]) -> dict[tuple[str, str], str]:
    paths = []
    for rel, body in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    result = extract(paths, cache_root=tmp_path / "graphify-out")
    return _qualified(result["nodes"], result["edges"])


def _module(name: str, body: str) -> str:
    return f"defmodule {name} do\n{body}end\n"


def test_fully_qualified_call(tmp_path: Path):
    calls = _calls(tmp_path, {
        "lib/app/accounts.ex": _ACCOUNTS,
        "lib/app/web.ex": _module("App.Web", (
            "  def show(id) do\n"
            "    App.Accounts.get_user(id)\n"
            "  end\n"
        )),
    })
    assert calls.get(("App.Web.show", "App.Accounts.get_user")) == "EXTRACTED"


def test_aliased_call(tmp_path: Path):
    calls = _calls(tmp_path, {
        "lib/app/accounts.ex": _ACCOUNTS,
        "lib/app/web.ex": _module("App.Web", (
            "  alias App.Accounts\n"
            "\n"
            "  def show(id) do\n"
            "    Accounts.get_user(id)\n"
            "  end\n"
        )),
        "lib/app/local.ex": _module("App.Local", (
            "  def show(id) do\n"
            "    alias App.Accounts\n"
            "    Accounts.get_user(id)\n"
            "  end\n"
        )),
    })
    assert calls.get(("App.Web.show", "App.Accounts.get_user")) == "EXTRACTED"
    assert calls.get(("App.Local.show", "App.Accounts.get_user")) == "EXTRACTED"


def test_alias_as(tmp_path: Path):
    calls = _calls(tmp_path, {
        "lib/app/accounts.ex": _ACCOUNTS,
        "lib/app/web.ex": _module("App.Web", (
            "  alias App.Accounts, as: Acc\n"
            "\n"
            "  def show(id) do\n"
            "    Acc.get_user(id)\n"
            "  end\n"
        )),
    })
    assert calls.get(("App.Web.show", "App.Accounts.get_user")) == "EXTRACTED"


def test_multi_alias(tmp_path: Path):
    calls = _calls(tmp_path, {
        "lib/app/accounts.ex": _ACCOUNTS,
        "lib/app/repo.ex": _REPO,
        "lib/app/web.ex": _module("App.Web", (
            "  alias App.{Accounts, Repo}\n"
            "\n"
            "  def show(id) do\n"
            "    Accounts.get_user(id)\n"
            "  end\n"
            "\n"
            "  def save(x) do\n"
            "    Repo.insert(x)\n"
            "  end\n"
        )),
    })
    assert calls.get(("App.Web.show", "App.Accounts.get_user")) == "EXTRACTED"
    assert calls.get(("App.Web.save", "App.Repo.insert")) == "EXTRACTED"


def test_dunder_module(tmp_path: Path):
    calls = _calls(tmp_path, {
        "lib/app/web/helpers.ex": _module("App.Web.Helpers", (
            "  def fmt(x) do\n"
            "    x\n"
            "  end\n"
        )),
        "lib/app/web.ex": _module("App.Web", (
            "  alias __MODULE__.Helpers, as: H\n"
            "\n"
            "  def show(x) do\n"
            "    __MODULE__.Helpers.fmt(x)\n"
            "  end\n"
            "\n"
            "  def show_aliased(x) do\n"
            "    H.fmt(x)\n"
            "  end\n"
            "\n"
            "  def again(x) do\n"
            "    __MODULE__.show(x)\n"
            "  end\n"
        )),
    })
    assert calls.get(("App.Web.show", "App.Web.Helpers.fmt")) == "EXTRACTED"
    assert calls.get(("App.Web.show_aliased", "App.Web.Helpers.fmt")) == "EXTRACTED"
    assert calls.get(("App.Web.again", "App.Web.show")) == "EXTRACTED"


def test_nested_module_auto_alias(tmp_path: Path):
    calls = _calls(tmp_path, {
        "lib/app/web.ex": _module("App.Web", (
            "  defmodule Helpers do\n"
            "    def fmt(x) do\n"
            "      x\n"
            "    end\n"
            "  end\n"
            "\n"
            "  def show(x) do\n"
            "    Helpers.fmt(x)\n"
            "  end\n"
        )),
    })
    assert calls.get(("App.Web.show", "Helpers.fmt")) == "EXTRACTED"


def test_remote_call_does_not_bind_to_own_same_named_def(tmp_path: Path):
    calls = _calls(tmp_path, {
        "lib/app/repo.ex": _REPO,
        "lib/app/admin.ex": _module("App.Admin", (
            "  def save(x) do\n"
            "    App.Repo.insert(x)\n"
            "  end\n"
            "\n"
            "  def insert(x) do\n"
            "    x\n"
            "  end\n"
        )),
    })
    assert ("App.Admin.save", "App.Admin.insert") not in calls
    assert calls.get(("App.Admin.save", "App.Repo.insert")) == "EXTRACTED"


def test_external_module_emits_nothing(tmp_path: Path):
    calls = _calls(tmp_path, {
        "lib/app/repo.ex": _REPO,
        "lib/app/admin.ex": _module("App.Admin", (
            "  alias MyDep.Repo\n"
            "\n"
            "  def save(x) do\n"
            "    Repo.insert(x)\n"
            "    Enum.map(x, & &1)\n"
            "    Map.update(x, :k, 0, & &1)\n"
            "  end\n"
            "\n"
            "  def insert(x), do: x\n"
            "  def map(x), do: x\n"
            "  def update(x), do: x\n"
        )),
    })
    assert not [pair for pair in calls if pair[0] == "App.Admin.save"]


def test_variable_receiver_stays_unlinked(tmp_path: Path):
    calls = _calls(tmp_path, {
        "lib/app/repo.ex": _REPO,
        "lib/app/admin.ex": _module("App.Admin", (
            "  def save(mod, conn) do\n"
            "    mod.insert(conn.assigns)\n"
            "  end\n"
            "\n"
            "  def insert(x), do: x\n"
            "  def assigns(x), do: x\n"
        )),
    })
    assert not [pair for pair in calls if pair[0] == "App.Admin.save"]


def test_import_and_local_calls_unchanged(tmp_path: Path):
    calls = _calls(tmp_path, {
        "lib/app/repo.ex": _REPO,
        "lib/app/web.ex": _module("App.Web", (
            "  import App.Repo\n"
            "\n"
            "  def create(attrs) do\n"
            "    insert(attrs)\n"
            "  end\n"
            "\n"
            "  def create_local(attrs) do\n"
            "    build(attrs)\n"
            "  end\n"
            "\n"
            "  defp build(attrs) do\n"
            "    attrs\n"
            "  end\n"
        )),
    })
    assert calls.get(("App.Web.create", "App.Repo.insert")) == "INFERRED"
    assert calls.get(("App.Web.create_local", "App.Web.build")) == "EXTRACTED"


def test_qualified_call_survives_incremental_rebuild(tmp_path: Path):
    """On `graphify update` the unchanged callee file arrives only as
    resolution-context nodes and edges; the call must still resolve."""
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "accounts.ex").write_text(_ACCOUNTS, encoding="utf-8")
    caller = corpus / "web.ex"

    def _caller(extra: str = "") -> str:
        return _module("App.Web", (
            "  alias App.Accounts\n"
            "\n"
            "  def show(id) do\n"
            "    Accounts.get_user(id)\n"
            "  end\n"
            f"{extra}"
        ))

    caller.write_text(_caller(), encoding="utf-8")
    graph_path = corpus / "graphify-out" / "graph.json"

    def calls() -> dict[tuple[str, str], str]:
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        return _qualified(data["nodes"], data["links"])

    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    assert calls().get(("App.Web.show", "App.Accounts.get_user")) == "EXTRACTED"

    caller.write_text(_caller("\n  def other, do: :ok\n"), encoding="utf-8")
    assert _rebuild_code(corpus, changed_paths=[caller], no_cluster=True,
                         acquire_lock=False) is True
    assert calls().get(("App.Web.show", "App.Accounts.get_user")) == "EXTRACTED"
