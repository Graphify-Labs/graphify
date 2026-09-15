"""Regression tests for #3562: Elixir alias/import edges must land on the
``defmodule`` node they name, instead of dangling on a name-derived id.

``extract_elixir`` mints a module DEFINITION as ``_make_id(_file_stem(path),
module_name)`` — the corpus-wide invariant documented on ``_file_stem`` (#1504),
which keeps same-named symbols in different files from collapsing into one
last-writer-wins node. But it emitted the REFERENCE side of an
``alias``/``import``/``require``/``use`` as ``_make_id(module_name)``, with no
stem. So defining ``MyApp.Repo`` in ``lib/my_app/repo.ex`` produced the node id
``lib_my_app_repo_myapp_repo`` while ``alias MyApp.Repo`` produced the edge
target ``myapp_repo``. Those can never be equal, so ``build_from_json``'s
``if src not in node_set or tgt not in node_set: continue`` prune dropped EVERY
Elixir alias/import edge — silently: extraction reported success, both nodes
existed, only the edge was missing, leaving the graph almost entirely
intra-file. (``extract_elixir``'s own ``clean_edges`` filter deliberately
exempts ``imports``, i.e. it already assumed a downstream pass would resolve
them. Nothing did.)

An Elixir alias names a BEAM module, not a path, so the per-file extractor
cannot resolve it — the same shape as Kotlin #2526. Fixed the same way: the
extractor stamps the written name as ``metadata.target_fqn`` and
``_resolve_elixir_import_targets`` (run from ``extract()``, before the
import-evidence index is built) repoints the edge onto the one module node with
that exact label. Zero or several candidates leave the edge alone — externals
(``Ecto.Query``, ``Logger``) keep dangling and are pruned by build, and NO stub
node is ever fabricated for them.
"""
from __future__ import annotations

import os
from pathlib import Path

from graphify.build import build_from_json
from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _elixir_project(tmp_path: Path) -> tuple[Path, list[Path]]:
    """A miniature Phoenix-shaped app: aliases, multi-alias, use, and externals.

    realpath: on macOS pytest's tmp dir lives under /private/var but is handed
    out as /var — extract() resolves paths, so anchor on the resolved form.
    """
    root = Path(os.path.realpath(tmp_path))
    paths = [
        _write(
            root / "lib/my_app/accounts/user.ex",
            """defmodule MyApp.Accounts.User do
  alias MyApp.Repo
  alias MyApp.Schemas.{Account, Token}
  use MyAppWeb
  import Ecto.Query
  require Logger

  def create(attrs) do
    Repo.insert(attrs)
  end
end
""",
        ),
        _write(
            root / "lib/my_app/repo.ex",
            "defmodule MyApp.Repo do\n  def insert(x), do: x\nend\n",
        ),
        _write(
            root / "lib/my_app/schemas/account.ex",
            "defmodule MyApp.Schemas.Account do\n  def new, do: %{}\nend\n",
        ),
        _write(
            root / "lib/my_app/schemas/token.ex",
            "defmodule MyApp.Schemas.Token do\n  def new, do: %{}\nend\n",
        ),
        _write(
            root / "lib/my_app_web.ex",
            "defmodule MyAppWeb do\n  def router, do: :ok\nend\n",
        ),
    ]
    return root, paths


# Modules the fixture corpus actually defines, and the external ones it names
# but does not define.
_IN_CORPUS = {
    "MyApp.Repo",
    "MyApp.Schemas.Account",
    "MyApp.Schemas.Token",
    "MyAppWeb",
}
_EXTERNAL = {"Ecto.Query", "Logger"}


def _imports(result: dict) -> list[dict]:
    return [e for e in result["edges"] if e.get("relation") == "imports"]


def _node_by_label(result: dict, label: str) -> dict:
    matches = [n for n in result["nodes"] if n.get("label") == label]
    assert len(matches) == 1, f"expected exactly one {label!r} node, got {matches}"
    return matches[0]


def _fqn(edge: dict) -> str:
    return str((edge.get("metadata") or {}).get("target_fqn") or "")


def test_elixir_alias_target_equals_defmodule_node_id(tmp_path: Path):
    """The defining node id and the alias edge target must be the SAME string."""
    root, paths = _elixir_project(tmp_path)
    result = extract(paths, cache_root=root)

    repo_node = _node_by_label(result, "MyApp.Repo")
    alias_edges = [e for e in _imports(result) if _fqn(e) == "MyApp.Repo"]
    assert alias_edges, "no imports edge for `alias MyApp.Repo`"
    for e in alias_edges:
        assert e["target"] == repo_node["id"], (
            f"alias target {e['target']!r} != defmodule node id {repo_node['id']!r}"
        )


def test_elixir_definition_ids_keep_their_file_stem(tmp_path: Path):
    """The fix must NOT be 'drop the stem from the definition id' (#1504).

    Dropping it is the tempting one-liner, but function ids are
    ``_make_id(module_nid, func_name)``, so a stemless ``def router`` in
    ``MyAppWeb`` would collapse onto the module ``MyAppWeb.Router`` — the
    ``use MyAppWeb, :router`` idiom of every Phoenix app.
    """
    root, paths = _elixir_project(tmp_path)
    result = extract(paths, cache_root=root)

    for label, stem in (
        ("MyApp.Repo", "lib_my_app_repo"),
        ("MyApp.Schemas.Account", "lib_my_app_schemas_account"),
        ("MyAppWeb", "lib_my_app_web"),
    ):
        nid = _node_by_label(result, label)["id"]
        assert nid.startswith(stem + "_"), (
            f"{label} node id {nid!r} lost its file-stem prefix {stem!r}"
        )
    assert len({n["id"] for n in result["nodes"]}) == len(result["nodes"]), (
        "node ids collided"
    )


def test_elixir_no_dangling_import_for_in_corpus_module(tmp_path: Path):
    """Every alias/import naming a module DEFINED in the corpus must resolve."""
    root, paths = _elixir_project(tmp_path)
    result = extract(paths, cache_root=root)

    node_ids = {n["id"] for n in result["nodes"]}
    resolved = set()
    for e in _imports(result):
        fqn = _fqn(e)
        assert fqn, f"imports edge carries no target_fqn: {e}"
        if fqn in _IN_CORPUS:
            assert e["target"] in node_ids, (
                f"dangling imports edge for in-corpus module {fqn}: "
                f"target {e['target']!r} is not a node"
            )
            resolved.add(fqn)
    assert resolved == _IN_CORPUS, f"missing import edges for {_IN_CORPUS - resolved}"


def test_elixir_external_modules_dangle_without_stub_node(tmp_path: Path):
    """`import Ecto.Query` / `require Logger` keep their edge, mint no node.

    Externals have no definition in the corpus, so the designed behaviour is the
    same as every other language's external imports: the edge stays name-derived
    and build prunes it. Fabricating a stub node instead would put a phantom
    ``Ecto.Query`` in the graph (the ghost-node failure of #2195).
    """
    root, paths = _elixir_project(tmp_path)
    result = extract(paths, cache_root=root)

    node_ids = {n["id"] for n in result["nodes"]}
    node_labels = {n.get("label") for n in result["nodes"]}
    seen = set()
    for e in _imports(result):
        fqn = _fqn(e)
        if fqn in _EXTERNAL:
            seen.add(fqn)
            assert e["target"] not in node_ids, (
                f"external module {fqn} was resolved to a node — a stub was fabricated"
            )
    assert seen == _EXTERNAL, f"missing import edges for {_EXTERNAL - seen}"
    for fqn in _EXTERNAL:
        assert fqn not in node_labels, f"stub node minted for external module {fqn}"


def test_elixir_import_edges_survive_build(tmp_path: Path):
    """The user-visible claim: the edges are still there after graph assembly."""
    root, paths = _elixir_project(tmp_path)
    result = extract(paths, cache_root=root)
    G = build_from_json(result, directed=True)

    kept = [
        (u, v) for u, v, d in G.edges(data=True) if d.get("relation") == "imports"
    ]
    assert len(kept) == len(_IN_CORPUS), (
        f"expected {len(_IN_CORPUS)} surviving import edges, got {len(kept)}: {kept}"
    )
    user_file = next(
        n["id"] for n in result["nodes"] if n.get("label") == "user.ex"
    )
    repo_module = _node_by_label(result, "MyApp.Repo")["id"]
    assert (user_file, repo_module) in kept
    # The externals were pruned, not turned into nodes.
    for fqn in _EXTERNAL:
        assert fqn not in {G.nodes[n].get("label") for n in G.nodes}


def test_elixir_ambiguous_module_name_is_left_unresolved(tmp_path: Path):
    """Two files defining the same module => no guess (single-candidate guard).

    Picking one would be a fabricated edge. The edge stays dangling, exactly as
    it did before the fix, rather than becoming wrong.
    """
    root = Path(os.path.realpath(tmp_path))
    paths = [
        _write(
            root / "lib/a.ex",
            "defmodule MyApp.Dup do\n  def go, do: :a\nend\n",
        ),
        _write(
            root / "test/support/b.ex",
            "defmodule MyApp.Dup do\n  def go, do: :b\nend\n",
        ),
        _write(
            root / "lib/caller.ex",
            "defmodule MyApp.Caller do\n  alias MyApp.Dup\n  def go, do: Dup.go()\nend\n",
        ),
    ]
    result = extract(paths, cache_root=root)

    node_ids = {n["id"] for n in result["nodes"]}
    dup_edges = [e for e in _imports(result) if _fqn(e) == "MyApp.Dup"]
    assert dup_edges, "no imports edge for `alias MyApp.Dup`"
    for e in dup_edges:
        assert e["target"] not in node_ids, (
            "ambiguous module name must not be resolved to an arbitrary candidate"
        )


def test_elixir_self_import_preserves_contains_edge(tmp_path: Path):
    """A module that imports ITSELF must not destroy its own `contains` edge.

    The `__using__`/`quote do import MyApp.Context end` idiom makes a file
    alias a module it also defines. Retargeting that import onto the defmodule
    node lands it on the same (source, target) pair as `file --contains-->
    module`; the built graph is a plain non-multi Graph, so one relation would
    silently overwrite the other. Measured at 17 lost `contains` edges on a
    980-file app before the self-import guard.
    """
    root = Path(os.path.realpath(tmp_path))
    paths = [_write(
        root / "lib/my_app/context.ex",
        """defmodule MyApp.Context do
  defmacro __using__(_) do
    quote do
      import MyApp.Context
    end
  end

  def helper(x), do: x
end
""",
    )]
    result = extract(paths, cache_root=tmp_path / "cache", root=str(root))
    graph = build_from_json(result, root=str(root), directed=False)
    relations = {d.get("relation") for _, _, d in graph.edges(data=True)}
    assert "contains" in relations, (
        "self-import overwrote the file --contains--> module edge"
    )


def test_elixir_nested_defmodule_does_not_capture_foreign_alias(tmp_path: Path):
    """A nested `defmodule` must never absorb another file's alias.

    `extract_elixir` labels a nested module with the name as WRITTEN, not its
    real BEAM name: `defmodule Supervisor` inside `MyApp.Application` is
    labelled `Supervisor`, not `MyApp.Application.Supervisor`. Indexing it
    would let it capture `use Supervisor` — the Elixir stdlib module — from
    unrelated files and assert a false EXTRACTED edge. Only top-level
    defmodules carry the `_elixir_module` marker the resolver indexes on.
    """
    root = Path(os.path.realpath(tmp_path))
    paths = [
        _write(
            root / "lib/my_app/application.ex",
            """defmodule MyApp.Application do
  defmodule Supervisor do
    def start_link(_), do: :ok
  end

  def start(_type, _args), do: :ok
end
""",
        ),
        _write(
            root / "lib/my_app/workers/pool.ex",
            "defmodule MyApp.Workers.Pool do\n  use Supervisor\n  def init(_), do: :ok\nend\n",
        ),
    ]
    result = extract(paths, cache_root=tmp_path / "cache", root=str(root))
    node_ids = {n["id"] for n in result["nodes"]}
    captured = [
        e for e in _imports(result)
        if "pool.ex" in str(e.get("source_file") or "") and e["target"] in node_ids
    ]
    assert captured == [], (
        f"nested defmodule captured a foreign alias: {captured}"
    )


def test_elixir_resolution_survives_incremental_rebuild(tmp_path: Path):
    """An alias into an UNCHANGED file must still resolve on a partial re-extract.

    On an incremental run `all_nodes` holds only the re-extracted batch, so
    resolving against it drops every alias pointing into an unchanged file —
    the graph would decay back toward the bug on the `graphify watch` / hook
    path — and would also bypass the single-candidate guard, since a
    corpus-wide-ambiguous name can look unique within the changed subset. The
    resolver therefore indexes `resolution_nodes`, which includes the
    caller-supplied unchanged-corpus nodes (#2406).
    """
    root = Path(os.path.realpath(tmp_path))
    paths = [
        _write(
            root / "lib/my_app/repo.ex",
            "defmodule MyApp.Repo do\n  def insert(x), do: x\nend\n",
        ),
        _write(
            root / "lib/my_app/user.ex",
            """defmodule MyApp.User do
  alias MyApp.Repo

  def save(x), do: Repo.insert(x)
end
""",
        ),
    ]
    full = extract(paths, cache_root=tmp_path / "c1", root=str(root))
    full_ids = {n["id"] for n in full["nodes"]}
    resolved_full = [e for e in _imports(full) if e["target"] in full_ids]
    assert len(resolved_full) == 1

    # Re-extract ONLY user.ex; repo.ex arrives as unchanged-corpus context.
    context = [n for n in full["nodes"] if "repo.ex" in str(n.get("source_file") or "")]
    incremental = extract(
        [root / "lib/my_app/user.ex"],
        cache_root=tmp_path / "c2",
        root=str(root),
        resolution_context_nodes=context,
    )
    known = {n["id"] for n in incremental["nodes"]} | {n["id"] for n in context}
    resolved_inc = [e for e in _imports(incremental) if e["target"] in known]
    assert len(resolved_inc) == 1, (
        "alias into an unchanged file did not resolve on incremental rebuild"
    )
    assert resolved_inc[0]["target"] == resolved_full[0]["target"]
