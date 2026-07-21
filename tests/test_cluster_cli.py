"""`graphify cluster` CLI surface (init/add/remove/locate/build/check/status)."""
import json

import pytest

from graphify.cluster_cli import cmd_cluster
from graphify.cluster_graph import load_local_config, load_spec
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
    code, _out, err = _run([], capsys)
    assert code == 0
    assert "cluster-only" in err  # disambiguation from community detection


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
    _out, err = capsys.readouterr()
    assert "Manage cluster graphs" in err
