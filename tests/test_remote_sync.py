"""Tests for the central graph store (graphify.store) and push/pull hooks (graphify.remote).

Covers:
  - graphify.store.find_config / store_context        (.graphify/config.json discovery)
  - graphify.store.ensure_out_link                    (graphify-out -> store link, migration,
                                                       branch retarget, .gitignore upkeep)
  - graphify.remote push/pull                         (hook resolution + invocation)

All offline: no network, no boto3. Git repos are real `git init` under tmp_path;
hooks are tiny local scripts. No side effects outside tmp_path.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from graphify import remote, store


def _git_repo(d: Path) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(d)], check=True)
    return d


def _write_config(d: Path, **cfg) -> None:
    (d / ".graphify").mkdir(exist_ok=True)
    (d / ".graphify" / "config.json").write_text(json.dumps(cfg))


# --------------------------------------------------------------- config discovery

def test_find_config_walks_up(tmp_path):
    repo = tmp_path / "r"
    (repo / "a" / "b").mkdir(parents=True)
    _write_config(repo, store=str(tmp_path / "s"))
    found = store.find_config(repo / "a" / "b")
    assert found is not None
    cfg, root = found
    assert root == (repo).resolve() and cfg["store"] == str(tmp_path / "s")


def test_find_config_malformed_returns_none(tmp_path):
    (tmp_path / ".graphify").mkdir()
    (tmp_path / ".graphify" / "config.json").write_text("{ not json")
    assert store.find_config(tmp_path) is None


def test_store_context_none_without_store_key(tmp_path):
    _write_config(tmp_path, push="./x.py")  # config exists but no "store"
    assert store.store_context(tmp_path) is None


def test_store_root_is_store_base_no_repo_branch(tmp_path):
    # the store path IS the key — no <repo>/<branch> segments appended
    repo = _git_repo(tmp_path / "some-local-name")
    _write_config(repo, store=str(tmp_path / "s"))
    ctx = store.store_context(repo)
    assert ctx is not None
    assert ctx["store_root"] == (tmp_path / "s")
    assert ctx["store_base"] == (tmp_path / "s")


def test_origin_remote_does_not_affect_store_path(tmp_path):
    # the origin URL is irrelevant now — the config's store path is the whole key
    clone = _git_repo(tmp_path / "whatever-local-name")
    subprocess.run(
        ["git", "-C", str(clone), "remote", "add", "origin",
         "git@github.com:acme/mono.git"],
        check=True,
    )
    _write_config(clone, store=str(tmp_path / "s"))
    ctx = store.store_context(clone)
    assert ctx is not None
    assert ctx["store_root"] == (tmp_path / "s")


def test_find_config_non_dict_json_returns_none(tmp_path):
    (tmp_path / ".graphify").mkdir()
    (tmp_path / ".graphify" / "config.json").write_text('["not", "a", "dict"]')
    assert store.find_config(tmp_path) is None


def test_store_context_non_string_store_returns_none(tmp_path):
    _write_config(tmp_path, store=123)
    assert store.store_context(tmp_path) is None


def test_store_tilde_expands_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    repo = _git_repo(tmp_path / "r")
    _write_config(repo, store="~/gstore")
    ctx = store.store_context(repo)
    assert ctx is not None
    assert ctx["store_base"] == tmp_path / "gstore"


# --------------------------------------------------------------- ensure_out_link

def test_no_config_is_noop(tmp_path):
    assert store.ensure_out_link(tmp_path) is None
    assert not (tmp_path / "graphify-out").exists()


def test_link_created_and_writes_land_in_store(tmp_path):
    repo = _git_repo(tmp_path / "myrepo")
    _write_config(repo, store=str(tmp_path / "store"))
    target = store.ensure_out_link(repo)
    assert target == (tmp_path / "store" / "graphify-out").resolve()
    link = repo / "graphify-out"
    assert store._is_link(link)
    # a write through the link physically lands in the store
    (link / "graph.json").write_text("{}")
    assert (target / "graph.json").is_file()
    assert not (repo / "graphify-out" / "graph.json").resolve().is_relative_to(repo.resolve())


def test_module_link_keyed_by_relpath(tmp_path):
    repo = _git_repo(tmp_path / "mono")
    module = repo / "services" / "api"
    module.mkdir(parents=True)
    _write_config(repo, store=str(tmp_path / "store"))
    target = store.ensure_out_link(module)
    assert target == (
        tmp_path / "store" / "services" / "api" / "graphify-out"
    ).resolve()
    assert store._is_link(module / "graphify-out")


def test_idempotent_second_call(tmp_path):
    repo = _git_repo(tmp_path / "r")
    _write_config(repo, store=str(tmp_path / "store"))
    first = store.ensure_out_link(repo)
    second = store.ensure_out_link(repo)
    assert first == second and store._is_link(repo / "graphify-out")
    # gitignore entry not duplicated
    lines = (repo / ".gitignore").read_text().splitlines()
    assert lines.count("graphify-out") == 1


def test_branch_switch_keeps_same_link(tmp_path):
    # the repo points at the same store location on every branch — no retarget,
    # no rebuild. The graph built on one branch is right there on the next.
    repo = _git_repo(tmp_path / "r")
    _write_config(repo, store=str(tmp_path / "store"))
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "-C", str(repo), "commit", "--allow-empty", "-q", "-m", "x"],
                   check=True, env=env)
    main_target = store.ensure_out_link(repo)
    (main_target / "graph.json").write_text('{"built": true}')

    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "feat/x"], check=True)
    feat_target = store.ensure_out_link(repo)
    assert feat_target == main_target  # same store location, regardless of branch
    # the graph built on main is immediately visible on the new branch
    assert (repo / "graphify-out" / "graph.json").read_text() == '{"built": true}'


def test_migrates_existing_local_dir(tmp_path, capsys):
    repo = _git_repo(tmp_path / "r")
    _write_config(repo, store=str(tmp_path / "store"))
    local = repo / "graphify-out"
    (local / "wiki").mkdir(parents=True)
    (local / "graph.json").write_text('{"old": true}')
    (local / "wiki" / "index.md").write_text("# hi")

    target = store.ensure_out_link(repo)
    assert store._is_link(local)
    assert (target / "graph.json").read_text() == '{"old": true}'
    assert (target / "wiki" / "index.md").is_file()
    assert "migrated" in capsys.readouterr().out


def test_migration_collision_local_wins(tmp_path):
    # store already has an (older) graph; the local build is freshest and wins
    repo = _git_repo(tmp_path / "r")
    _write_config(repo, store=str(tmp_path / "store"))
    target = tmp_path / "store" / "graphify-out"
    target.mkdir(parents=True)
    (target / "graph.json").write_text('{"stale": true}')
    local = repo / "graphify-out"
    local.mkdir()
    (local / "graph.json").write_text('{"fresh": true}')

    store.ensure_out_link(repo)
    assert (target / "graph.json").read_text() == '{"fresh": true}'


def test_dangling_link_self_heals(tmp_path):
    import shutil
    repo = _git_repo(tmp_path / "r")
    _write_config(repo, store=str(tmp_path / "store"))
    target = store.ensure_out_link(repo)
    shutil.rmtree(tmp_path / "store")  # store wiped (new machine, cleanup, …)
    assert store.ensure_out_link(repo) == target
    assert target.is_dir()  # recreated; link still valid


def test_regular_file_named_graphify_out_is_never_clobbered(tmp_path, capsys):
    repo = _git_repo(tmp_path / "r")
    _write_config(repo, store=str(tmp_path / "store"))
    rogue = repo / "graphify-out"
    rogue.write_text("user data, not a dir")
    store.ensure_out_link(repo)  # must not raise
    assert rogue.read_text() == "user data, not a dir"
    assert not store._is_link(rogue)
    assert "not linking" in capsys.readouterr().err


def test_custom_relative_out_name_links_too(tmp_path, monkeypatch):
    from graphify import paths
    monkeypatch.setattr(paths, "GRAPHIFY_OUT", "graphify-out-feature")
    monkeypatch.setattr(paths, "GRAPHIFY_OUT_NAME", "graphify-out-feature")
    repo = _git_repo(tmp_path / "r")
    _write_config(repo, store=str(tmp_path / "store"))
    target = store.ensure_out_link(repo)
    assert target == (tmp_path / "store" / "graphify-out-feature").resolve()
    assert store._is_link(repo / "graphify-out-feature")
    assert "graphify-out-feature" in (repo / ".gitignore").read_text().splitlines()


def test_gitignore_created_with_bare_entry(tmp_path):
    repo = _git_repo(tmp_path / "r")
    _write_config(repo, store=str(tmp_path / "store"))
    store.ensure_out_link(repo)
    lines = (repo / ".gitignore").read_text().splitlines()
    # bare entry: "graphify-out/" (dirs only) would NOT match a symlink
    assert "graphify-out" in lines


def test_gitignore_slash_only_entry_gets_bare_added(tmp_path):
    repo = _git_repo(tmp_path / "r")
    (repo / ".gitignore").write_text("node_modules\ngraphify-out/\n")
    _write_config(repo, store=str(tmp_path / "store"))
    store.ensure_out_link(repo)
    lines = (repo / ".gitignore").read_text().splitlines()
    assert "graphify-out" in lines and "node_modules" in lines


def test_gitignore_existing_bare_entry_untouched(tmp_path):
    repo = _git_repo(tmp_path / "r")
    (repo / ".gitignore").write_text("graphify-out\n")
    _write_config(repo, store=str(tmp_path / "store"))
    store.ensure_out_link(repo)
    assert (repo / ".gitignore").read_text() == "graphify-out\n"


def test_gitignore_doublestar_entry_accepted(tmp_path):
    repo = _git_repo(tmp_path / "r")
    (repo / ".gitignore").write_text("**/graphify-out\n")
    _write_config(repo, store=str(tmp_path / "store"))
    store.ensure_out_link(repo)
    assert (repo / ".gitignore").read_text() == "**/graphify-out\n"  # no duplicate


def test_gitignore_without_trailing_newline(tmp_path):
    repo = _git_repo(tmp_path / "r")
    (repo / ".gitignore").write_text("node_modules")  # no trailing \n
    _write_config(repo, store=str(tmp_path / "store"))
    store.ensure_out_link(repo)
    assert (repo / ".gitignore").read_text().splitlines() == ["node_modules", "graphify-out"]


def test_link_all_without_store_dir_returns_zero(tmp_path):
    repo = _git_repo(tmp_path / "r")
    _write_config(repo, store=str(tmp_path / "store"))  # store never created
    ctx = store.store_context(repo)
    assert store.link_all(ctx) == 0


def test_materialize_skips_real_dirs_and_handles_dangling(tmp_path):
    import shutil
    repo = _git_repo(tmp_path / "r")
    _write_config(repo, store=str(tmp_path / "store"))
    ctx = store.store_context(repo)
    # a real local dir (already materialized / never linked) must be untouched
    real = repo / "graphify-out"
    real.mkdir()
    (real / "keep.json").write_text("{}")
    assert store.materialize(ctx) == 0
    assert (real / "keep.json").is_file()
    # a dangling link (store deleted) becomes an empty real folder, no crash
    shutil.rmtree(real)
    target = store.ensure_out_link(repo)
    shutil.rmtree(tmp_path / "store")
    assert store.materialize(store.store_context(repo)) == 1
    assert real.is_dir() and not store._is_link(real)


def test_link_is_invisible_to_git(tmp_path):
    repo = _git_repo(tmp_path / "r")
    _write_config(repo, store=str(tmp_path / "store"))
    store.ensure_out_link(repo)
    ((repo / "graphify-out") / "graph.json").write_text("{}")
    out = subprocess.check_output(
        ["git", "-C", str(repo), "status", "--porcelain"], text=True
    )
    assert "graphify-out" not in out


def test_absolute_graphify_out_env_disables_linking(tmp_path, monkeypatch):
    from graphify import paths
    monkeypatch.setattr(paths, "GRAPHIFY_OUT", str(tmp_path / "abs-out"))
    repo = _git_repo(tmp_path / "r")
    _write_config(repo, store=str(tmp_path / "store"))
    assert store.ensure_out_link(repo) is None


def test_works_without_git(tmp_path):
    # no git repo: root falls back to the config dir; the store path is the key
    repo = tmp_path / "plain"
    repo.mkdir()
    _write_config(repo, store=str(tmp_path / "store"))
    target = store.ensure_out_link(repo)
    assert target == (tmp_path / "store" / "graphify-out").resolve()
    assert not (repo / ".gitignore").exists()  # gitignore upkeep only inside git


# --------------------------------------------------------------- push/pull hooks

_RECORD_HOOK = (
    "import os, pathlib\n"
    "pathlib.Path(os.environ['MARKER']).write_text('|'.join([\n"
    "  os.environ['GRAPHIFY_ACTION'],\n"
    "  os.environ['GRAPHIFY_STORE_DIR'],\n"
    "  os.environ['GRAPHIFY_PREFIX'],\n"
    "]))\n"
)


def _hook_setup(tmp_path, monkeypatch, **cfg_extra):
    repo = _git_repo(tmp_path / "repo")
    _write_config(repo, store=str(tmp_path / "store"), **cfg_extra)
    monkeypatch.chdir(repo)
    marker = tmp_path / "marker.txt"
    monkeypatch.setenv("MARKER", str(marker))
    return repo, marker


def test_push_runs_explicit_hook_with_context(tmp_path, monkeypatch):
    hook = tmp_path / "myhook.py"
    hook.write_text(_RECORD_HOOK)
    repo, marker = _hook_setup(tmp_path, monkeypatch, push=str(hook))

    remote.cmd_push([])
    action, store_dir, prefix = marker.read_text().split("|")
    assert action == "push"
    assert store_dir == str(tmp_path / "store")     # the store path itself — no repo/branch
    assert prefix == "store"                          # the store folder's basename
    assert Path(store_dir).is_dir()  # push pre-creates the store tree


def test_relative_hook_path_resolves_against_repo_root(tmp_path, monkeypatch):
    repo, marker = _hook_setup(tmp_path, monkeypatch, pull="hooks/pull.py")
    (repo / "hooks").mkdir()
    (repo / "hooks" / "pull.py").write_text(_RECORD_HOOK)
    sub = repo / "sub"
    sub.mkdir()
    monkeypatch.chdir(sub)  # run from a subdir: config + hook still found
    remote.cmd_pull([])
    assert marker.read_text().startswith("pull|")


def test_repo_local_hook_found_without_config_key(tmp_path, monkeypatch):
    # the committed .graphify/pull.py is auto-discovered — no config key needed
    repo, marker = _hook_setup(tmp_path, monkeypatch)
    (repo / ".graphify" / "pull.py").write_text(_RECORD_HOOK)
    remote.cmd_pull([])
    assert marker.read_text().startswith("pull|")


def test_hook_env_includes_config_store_and_root(tmp_path, monkeypatch):
    hook = tmp_path / "envhook.py"
    hook.write_text(
        "import os, pathlib\n"
        "pathlib.Path(os.environ['MARKER']).write_text('|'.join([\n"
        "  os.environ['GRAPHIFY_CONFIG'],\n"
        "  os.environ['GRAPHIFY_STORE'],\n"
        "  os.environ['GRAPHIFY_REPO_ROOT'],\n"
        "]))\n"
    )
    repo, marker = _hook_setup(tmp_path, monkeypatch, push=str(hook))
    remote.cmd_push([])
    cfg_path, store_base, repo_root = marker.read_text().split("|")
    assert cfg_path == str(repo / ".graphify" / "config.json")
    assert store_base == str(tmp_path / "store")
    assert Path(repo_root) == repo.resolve()


def test_hook_extension_priority_is_deterministic(tmp_path, monkeypatch):
    # both pull.py and pull.sh committed: .py wins (first in _HOOK_EXTS)
    repo, marker = _hook_setup(tmp_path, monkeypatch)
    (repo / ".graphify" / "pull.py").write_text(_RECORD_HOOK)
    (repo / ".graphify" / "pull.sh").write_text("exit 9")
    remote.cmd_pull([])
    assert marker.read_text().startswith("pull|")


def test_missing_hook_errors(tmp_path, monkeypatch):
    _hook_setup(tmp_path, monkeypatch)
    with pytest.raises(SystemExit):
        remote.cmd_push([])


def test_hook_failure_propagates(tmp_path, monkeypatch):
    hook = tmp_path / "bad.py"
    hook.write_text("import sys; sys.exit(3)")
    _hook_setup(tmp_path, monkeypatch, push=str(hook))
    with pytest.raises(SystemExit):
        remote.cmd_push([])


def test_no_store_config_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(_git_repo(tmp_path / "repo"))
    with pytest.raises(SystemExit):
        remote.cmd_pull([])


_POPULATE_STORE_HOOK = (
    # a "pull" that simulates downloading: writes root + module graphs into the store
    "import os, pathlib\n"
    "s = pathlib.Path(os.environ['GRAPHIFY_STORE_DIR'])\n"
    "for mod in ('graphify-out', 'services/api/graphify-out', 'gone/graphify-out'):\n"
    "    d = s / mod\n"
    "    d.mkdir(parents=True, exist_ok=True)\n"
    "    (d / 'graph.json').write_text('{}')\n"
)


def test_pull_recreates_module_links(tmp_path, monkeypatch, capsys):
    hook = tmp_path / "pull.py"
    hook.write_text(_POPULATE_STORE_HOOK)
    repo, _ = _hook_setup(tmp_path, monkeypatch, pull=str(hook))
    (repo / "services" / "api").mkdir(parents=True)  # module exists in the clone
    # note: repo has NO graphify-out anywhere yet — fresh clone

    remote.cmd_pull([])

    # root + module links exist and read the store data; 'gone' (module absent
    # from the working tree) was skipped, not invented
    assert store._is_link(repo / "graphify-out")
    assert (repo / "graphify-out" / "graph.json").is_file()
    assert store._is_link(repo / "services" / "api" / "graphify-out")
    assert (repo / "services" / "api" / "graphify-out" / "graph.json").is_file()
    assert not (repo / "gone").exists()
    assert "linked" in capsys.readouterr().out


def test_link_all_idempotent_and_counts(tmp_path):
    repo = _git_repo(tmp_path / "r")
    (repo / "m").mkdir()
    _write_config(repo, store=str(tmp_path / "store"))
    ctx = store.store_context(repo)
    for mod in ("graphify-out", "m/graphify-out"):
        (ctx["store_root"] / mod).mkdir(parents=True)
    assert store.link_all(ctx) == 2
    assert store.link_all(ctx) == 0  # second pass: everything already correct


def test_interpreter_by_extension(tmp_path):
    assert remote._interpreter(tmp_path / "h.py") == [sys.executable]
    assert remote._interpreter(tmp_path / "h.js") == ["node"]
    assert remote._interpreter(tmp_path / "h.sh") == ["bash"]
    assert remote._interpreter(tmp_path / "h.ps1")[0] == "powershell"
    assert remote._interpreter(tmp_path / "h.cmd") == ["cmd", "/c"]
    assert remote._interpreter(tmp_path / "h.bat") == ["cmd", "/c"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX exec bit")
def test_executable_hook_runs_directly(tmp_path):
    hook = tmp_path / "push"
    hook.write_text("#!/bin/sh\nexit 0\n")
    os.chmod(hook, 0o755)
    assert remote._interpreter(hook) == []


def test_init_bootstraps_repo_dot_graphify(tmp_path, monkeypatch):
    # one command in a bare repo: .graphify/ with config.json + both hooks appears
    repo = _git_repo(tmp_path / "r")
    monkeypatch.chdir(repo)
    remote.cmd_init([])
    cfg = json.loads((repo / ".graphify" / "config.json").read_text())
    assert cfg["store"] == "~/graphify-store/r"  # default: ~/graphify-store/<folder>
    push = repo / ".graphify" / "push.py"
    pull = repo / ".graphify" / "pull.py"
    assert push.is_file() and pull.is_file()
    assert "GRAPHIFY_STORE_DIR" in push.read_text()
    assert "GRAPHIFY_STORE_DIR" in pull.read_text()
    # rerun keeps existing config and hooks
    push.write_text("# customized")
    (repo / ".graphify" / "config.json").write_text('{"store": "/custom"}')
    remote.cmd_init([])
    assert push.read_text() == "# customized"
    assert json.loads((repo / ".graphify" / "config.json").read_text())["store"] == "/custom"


def test_init_from_subdir_lands_at_config_root(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path / "r")
    _write_config(repo, store=str(tmp_path / "store"))
    sub = repo / "deep" / "down"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    remote.cmd_init([])
    assert (repo / ".graphify" / "push.py").is_file()
    assert not (sub / ".graphify").exists()


def test_remote_group_dispatch(monkeypatch):
    calls = []
    monkeypatch.setattr(remote, "cmd_init", lambda a: calls.append(("init", a)))
    monkeypatch.setattr(remote, "cmd_push", lambda a: calls.append(("push", a)))
    monkeypatch.setattr(remote, "cmd_pull", lambda a: calls.append(("pull", a)))
    monkeypatch.setattr(remote, "cmd_deinit", lambda a: calls.append(("delete", a)))
    for sub in ("init", "push", "pull", "delete", "deinit"):
        remote.cmd_remote([sub])
    assert [c[0] for c in calls] == ["init", "push", "pull", "delete", "delete"]
    with pytest.raises(SystemExit):
        remote.cmd_remote([])
    with pytest.raises(SystemExit):
        remote.cmd_remote(["bogus"])


def test_remote_delete_materializes_links(tmp_path, monkeypatch, capsys):
    # adopt: repo with root + module data in the store, links in place
    repo = _git_repo(tmp_path / "r")
    module = repo / "m"
    module.mkdir()
    _write_config(repo, store=str(tmp_path / "store"))
    root_target = store.ensure_out_link(repo)
    mod_target = store.ensure_out_link(module)
    (root_target / "graph.json").write_text('{"root": true}')
    (mod_target / "graph.json").write_text('{"mod": true}')
    monkeypatch.chdir(repo)

    remote.cmd_deinit([])

    for d, key in ((repo / "graphify-out", "root"), (module / "graphify-out", "mod")):
        assert not store._is_link(d) and d.is_dir()
        assert key in (d / "graph.json").read_text()
    # the store keeps its copy — other teammates/branches unaffected
    assert (root_target / "graph.json").is_file()
    assert (mod_target / "graph.json").is_file()
    assert "materialized 2" in capsys.readouterr().out


def test_init_respects_hook_in_other_language(tmp_path, monkeypatch):
    # a team already using push.sh must not get a competing push.py scaffolded
    repo = _git_repo(tmp_path / "r")
    (repo / ".graphify").mkdir()
    (repo / ".graphify" / "push.sh").write_text("#!/bin/sh\n")
    monkeypatch.chdir(repo)
    remote.cmd_init([])
    assert not (repo / ".graphify" / "push.py").exists()
    assert (repo / ".graphify" / "pull.py").is_file()


def test_init_outside_git_uses_cwd(tmp_path, monkeypatch):
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    monkeypatch.chdir(plain)
    remote.cmd_init([])
    assert (plain / ".graphify" / "config.json").is_file()


@pytest.mark.skipif(os.name == "nt", reason="POSIX exec bit")
def test_init_scaffolded_hooks_are_executable(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path / "r")
    monkeypatch.chdir(repo)
    remote.cmd_init([])
    for name in ("push.py", "pull.py"):
        hook = repo / ".graphify" / name
        assert os.access(hook, os.X_OK)  # shebang path: hook runs directly
        assert hook.read_text().startswith("#!")


def test_template_skip_excludes_cache_only(tmp_path, monkeypatch):
    # execute the shared template preamble offline and probe its skip()
    from graphify import remote_hook_templates as tpl
    monkeypatch.setenv("GRAPHIFY_ACTION", "push")
    monkeypatch.setenv("GRAPHIFY_STORE_DIR", str(tmp_path))
    monkeypatch.setenv("GRAPHIFY_PREFIX", "store")
    ns: dict = {}
    exec(tpl._COMMON, ns)
    assert ns["skip"]("graphify-out/cache/ast.json")
    assert ns["skip"]("services/api/graphify-out/cache/x.json")
    assert not ns["skip"]("graphify-out/graph.json")
    assert not ns["skip"]("services/api/graphify-out/wiki/index.md")


def test_init_backend_s3_public(tmp_path, monkeypatch):
    # --backend s3-public → .py hooks + a store_url config key; pull is URL-only (no boto3)
    repo = _git_repo(tmp_path / "r")
    monkeypatch.chdir(repo)
    remote.cmd_init(["--backend", "s3-public"])
    cfg = json.loads((repo / ".graphify" / "config.json").read_text())
    assert "store_url" in cfg
    pull = (repo / ".graphify" / "pull.py").read_text()
    assert "urllib" in pull and "boto3" not in pull
    assert "_manifest.json" in (repo / ".graphify" / "push.py").read_text()


def test_init_backend_git_lfs_and_rsync_write_shell(tmp_path, monkeypatch):
    for backend, marker in (("git-lfs", "GRAPHIFY_GIT_REMOTE"), ("rsync", "GRAPHIFY_RSYNC_DEST")):
        repo = _git_repo(tmp_path / backend)
        monkeypatch.chdir(repo)
        remote.cmd_init(["--backend", backend])
        assert (repo / ".graphify" / "push.sh").is_file()
        assert (repo / ".graphify" / "pull.sh").is_file()
        assert not (repo / ".graphify" / "push.py").exists()
        assert marker in (repo / ".graphify" / "push.sh").read_text()


def test_init_unknown_backend_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(_git_repo(tmp_path / "r"))
    with pytest.raises(SystemExit):
        remote.cmd_init(["--backend", "carrier-pigeon"])
