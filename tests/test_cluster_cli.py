"""`graphify cluster` CLI surface (init/add/remove/locate/build/check/status)."""
import json

import pytest

from graphify.cluster_cli import cmd_cluster
from graphify.cluster_graph import load_local_config, load_spec, resolve_member_path
from tests.test_cluster_build import make_member, write_cluster, _node


def _run(argv, capsys):
    """Run cmd_cluster, returning (exit_code, stdout, stderr)."""
    code = 0
    try:
        cmd_cluster(argv)
    except SystemExit as exc:
        code = exc.code or 0
    out, err = capsys.readouterr()
    return code, out, err


def _fake_checkout(path, url):
    (path / ".git").mkdir(parents=True)
    (path / ".git" / "config").write_text(
        f'[remote "origin"]\n\turl = {url}\n', encoding="utf-8"
    )


def test_usage_on_no_subcommand(capsys):
    code, out, _err = _run([], capsys)
    assert code == 0
    # Requested help goes to stdout (like `graphify --help`).
    assert "cluster-only" in out  # disambiguation from community detection


def test_unknown_subcommand_exits_1(capsys):
    code, _out, err = _run(["frobnicate"], capsys)
    assert code == 1
    assert "Usage" in err


def test_init_add_remove_flow(tmp_path, capsys):
    cluster = tmp_path / "my-cluster"
    code, out, _err = _run(["init", str(cluster), "--name", "demo"], capsys)
    assert code == 0 and "demo" in out
    # init is guarded against clobbering an existing spec
    code, _out, err = _run(["init", str(cluster)], capsys)
    assert code == 1 and "already exists" in err
    # .gitignore keeps local overrides and build output uncommitted
    gitignore = (cluster / ".gitignore").read_text(encoding="utf-8")
    assert "cluster.local.*" in gitignore and "graphify-out/" in gitignore

    repo = tmp_path / "alpha"
    _fake_checkout(repo, "https://github.com/org/alpha")
    code, out, _err = _run(["add", str(repo), "--dir", str(cluster)], capsys)
    assert code == 0
    spec = load_spec(cluster)
    assert spec.members[0].tag == "alpha"
    assert spec.members[0].url == "https://github.com/org/alpha"

    code, _out, err = _run(["add", str(repo), "--dir", str(cluster)], capsys)
    assert code == 1 and "already exists" in err

    code, _out, _err = _run(["remove", "alpha", "--dir", str(cluster)], capsys)
    assert code == 0
    assert load_spec(cluster).members == []


def test_add_relative_path_with_separate_cluster_dir(tmp_path, monkeypatch, capsys):
    invocation = tmp_path / "invocation"
    repo = invocation / "repos" / "alpha"
    _fake_checkout(repo, "https://github.com/org/alpha")
    cluster = tmp_path / "clusters" / "demo"
    write_cluster(cluster, [])
    monkeypatch.chdir(invocation)

    code, _out, err = _run(["add", "repos/alpha", "--dir", str(cluster)], capsys)
    assert code == 0, err
    member = load_spec(cluster).members[0]
    resolved, warnings = resolve_member_path(member, cluster, {})
    assert not warnings
    assert resolved == repo.resolve()


def test_add_via_symlinked_cluster_dir_stores_usable_hint(tmp_path, capsys):
    """relpath must use the UNRESOLVED cluster dir. A hint computed against the
    symlink-RESOLVED base carries that tree's `..` depth, but resolution later
    re-joins it against the unresolved dir with normpath (which does not follow
    symlinks) — with a symlink to a deeper real path, the hint climbs out of
    the wrong tree entirely (e.g. macOS /tmp -> /private/tmp)."""
    repo = tmp_path / "alpha"
    _fake_checkout(repo, "https://github.com/org/alpha")
    real_cluster = tmp_path / "d1" / "d2" / "cluster"
    write_cluster(real_cluster, [])
    (tmp_path / "s").symlink_to(tmp_path / "d1" / "d2")
    linked_cluster = tmp_path / "s" / "cluster"

    code, _out, err = _run(["add", str(repo), "--dir", str(linked_cluster)], capsys)
    assert code == 0, err
    member = load_spec(linked_cluster).members[0]
    resolved, _warnings = resolve_member_path(member, linked_cluster, {})
    assert resolved is not None and resolved.resolve() == repo.resolve()


def test_add_relative_path_falls_back_to_absolute_across_drives(
    tmp_path, monkeypatch, capsys
):
    repo = tmp_path / "alpha"
    _fake_checkout(repo, "https://github.com/org/alpha")
    cluster = tmp_path / "cluster"
    write_cluster(cluster, [])

    def _cross_drive(*_args):
        raise ValueError

    monkeypatch.setattr("graphify.cluster_cli.os.path.relpath", _cross_drive)

    code, _out, err = _run(["add", str(repo), "--dir", str(cluster)], capsys)
    assert code == 0, err
    assert load_spec(cluster).members[0].path == str(repo.resolve())


def test_add_invalid_tag_does_not_modify_spec(tmp_path, capsys):
    repo = tmp_path / "alpha"
    _fake_checkout(repo, "https://github.com/org/alpha")
    cluster = tmp_path / "cluster"
    write_cluster(cluster, [])
    spec_path = cluster / "cluster.json"
    before = spec_path.read_bytes()

    code, _out, err = _run(
        ["add", str(repo), "--as", "bad::tag", "--dir", str(cluster)], capsys
    )
    assert code == 1 and "invalid" in err
    assert spec_path.read_bytes() == before
    assert load_spec(cluster).members == []


def test_remove_blocks_when_links_reference_member(tmp_path, capsys):
    cluster = tmp_path / "cluster"
    write_cluster(cluster, [{"tag": "a", "path": "../a"}], links=[{
        "type": "api_call",
        "from": {"repo": "a", "label": "x"},
        "to": {"repo": "a", "label": "y"},
    }])
    code, _out, err = _run(["remove", "a", "--dir", str(cluster)], capsys)
    assert code == 1 and "referenced by links" in err


def test_locate_writes_local_override(tmp_path, capsys):
    cluster = tmp_path / "cluster"
    write_cluster(cluster, [{"tag": "a", "url": "https://github.com/org/a"}])
    checkout = tmp_path / "somewhere"
    _fake_checkout(checkout, "https://github.com/org/a")
    code, out, _err = _run(["locate", "a", str(checkout), "--dir", str(cluster)], capsys)
    assert code == 0
    cfg = load_local_config(cluster)
    assert cfg["paths"]["a"] == str(checkout.resolve())

    # mismatched origin still records, but warns
    other = tmp_path / "other"
    _fake_checkout(other, "https://github.com/org/unrelated")
    code, _out, err = _run(["locate", "a", str(other), "--dir", str(cluster)], capsys)
    assert code == 0 and "origin" in err


def test_build_and_status_end_to_end(tmp_path, capsys):
    make_member(tmp_path, "alpha", [_node("app", source_file="src/app.ts")])
    make_member(tmp_path, "beta", [_node("server", source_file="src/server.ts")])
    cluster = tmp_path / "cluster"
    write_cluster(cluster, [
        {"tag": "alpha", "path": "../alpha"},
        {"tag": "beta", "path": "../beta"},
    ], links=[{
        "type": "api_call",
        "from": {"repo": "alpha", "file": "src/app.ts"},
        "to": {"repo": "beta", "file": "src/server.ts"},
    }])

    code, out, _err = _run(["build", "--dir", str(cluster)], capsys)
    assert code == 0
    assert "2 members" in out
    assert "links: 1 edges" in out
    assert (cluster / "graphify-out" / "graph.json").is_file()

    code, out, _err = _run(["build", "--dir", str(cluster)], capsys)
    assert code == 0 and "skipped" in out

    code, out, _err = _run(["status", "--dir", str(cluster)], capsys)
    assert code == 0
    assert "alpha" in out and "ok" in out


def test_check_reports_and_exit_codes(tmp_path, capsys):
    make_member(tmp_path, "alpha", [_node("app", source_file="src/app.ts")])
    cluster = tmp_path / "cluster"
    write_cluster(cluster, [{"tag": "alpha", "path": "../alpha"}], links=[{
        "type": "api_call",
        "on_missing": "error",
        "from": {"repo": "alpha", "label": "missing-thing"},
        "to": {"repo": "alpha", "file": "src/app.ts"},
    }])
    code, _out, err = _run(["check", "--dir", str(cluster)], capsys)
    assert code == 1
    assert "no node matches" in err

    # Downgrade to warn -> check passes
    data = json.loads((cluster / "cluster.json").read_text(encoding="utf-8"))
    data["links"][0]["on_missing"] = "warn"
    (cluster / "cluster.json").write_text(json.dumps(data), encoding="utf-8")
    code, out, _err = _run(["check", "--dir", str(cluster)], capsys)
    assert code == 0 and "Spec OK" in out


def test_dispatch_routes_cluster_command(tmp_path, monkeypatch, capsys):
    """`graphify cluster ...` reaches cmd_cluster through dispatch_command."""
    import sys as _sys
    from graphify.cli import dispatch_command

    monkeypatch.setattr(_sys, "argv", ["graphify", "cluster", "help"])
    with pytest.raises(SystemExit) as exc:
        dispatch_command("cluster")
    assert exc.value.code == 0
    out, _err = capsys.readouterr()
    assert "Manage cluster graphs" in out


def test_flag_missing_value_is_a_hard_error(tmp_path, monkeypatch, capsys):
    """A value flag with no value must error, never fall through to a
    positional (`cluster init --name` used to create a dir named `--name`)."""
    monkeypatch.chdir(tmp_path)
    for argv in (
        ["init", "--name"],
        ["init", "--name="],
        ["init", "--dir"],
        ["init", "--name", "--dir", "d"],
    ):
        code, _out, err = _run(argv, capsys)
        assert code == 1, argv
        assert "requires a value" in err, argv
    assert not (tmp_path / "--name").exists()
    assert not (tmp_path / "--dir").exists()

    repo = tmp_path / "repo"
    repo.mkdir()
    assert _run(["init", "cl", "--name", "x"], capsys)[0] == 0
    code, _out, err = _run(["add", str(repo), "--as", "--dir", str(tmp_path / "cl")], capsys)
    assert code == 1 and "requires a value" in err


def test_unknown_flags_are_rejected(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code, _out, err = _run(["init", "--nmae", "typo"], capsys)
    assert code == 1 and "unknown option" in err
    assert not (tmp_path / "--nmae").exists() and not (tmp_path / "typo").exists()

    assert _run(["init", "cl", "--name", "x"], capsys)[0] == 0
    code, _out, err = _run(["remove", "tag", "--frob", "--dir", "cl"], capsys)
    assert code == 1 and "unknown option" in err


def test_help_tokens_never_reach_handlers(tmp_path, monkeypatch, capsys):
    """`cluster add --help` (any position) prints USAGE and exits 0 — it must
    never fall through to a handler and cause side effects."""
    monkeypatch.chdir(tmp_path)
    for argv in (["add", "--help"], ["init", "-h"], ["--help"], ["build", "-?"]):
        code, out, _err = _run(argv, capsys)
        assert code == 0, argv
        assert "Manage cluster graphs" in out, argv
    assert not any(p.is_dir() and p.name != "__pycache__" for p in tmp_path.iterdir())


def test_main_entrypoint_routes_cluster_help(tmp_path, monkeypatch, capsys):
    """The universal -h guard in __main__ defers to cluster's own USAGE."""
    import sys as _sys
    from graphify.__main__ import main

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(_sys, "argv", ["graphify", "cluster", "add", "--help"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    out, _err = capsys.readouterr()
    assert "Manage cluster graphs" in out
    assert not (tmp_path / "graphify-out").exists()


def test_add_rejects_cluster_dir_itself(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert _run(["init", "cl", "--name", "x"], capsys)[0] == 0
    code, _out, err = _run(["add", "cl", "--dir", "cl"], capsys)
    assert code == 1
    assert "own member" in err
    assert load_spec(tmp_path / "cl").members == []
