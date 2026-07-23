"""Member cluster-refs: the cluster-ref.json marker, --cluster flag, and hints."""
import json
import sys

import pytest

from graphify.cluster_graph import ClusterSpecError, build_cluster
from graphify.cluster_ref import (
    CLUSTER_REF_NAME,
    load_cluster_refs,
    resolve_cluster_dir,
    unresolvable_message,
)
from tests.test_cluster_build import make_member, write_cluster, _node
from tests.test_cluster_cli import _fake_checkout, _run


@pytest.fixture()
def built_cluster(tmp_path):
    """Two members + one declared link, cluster built once."""
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
    build_cluster(cluster)
    return cluster


def _marker(tmp_path, member):
    return tmp_path / member / "graphify-out" / CLUSTER_REF_NAME


def _only_ref(out_dir):
    refs = load_cluster_refs(out_dir)
    assert len(refs) == 1
    return refs[0]


# ---------------------------------------------------------------------------
# Writing markers
# ---------------------------------------------------------------------------

def test_build_writes_portable_markers(tmp_path, built_cluster):
    for member, tag in (("alpha", "alpha"), ("beta", "beta")):
        raw = _marker(tmp_path, member).read_text(encoding="utf-8")
        marker = json.loads(raw)
        assert marker["version"] == 1
        assert len(marker["clusters"]) == 1
        ref = marker["clusters"][0]
        assert ref["cluster_name"] == "test-cluster"
        assert ref["self_tag"] == tag
        assert ref["member_count"] == 2
        assert [m["tag"] for m in ref["members"]] == ["alpha", "beta"]
        assert ref["built_at"]
        # Committable: no absolute paths anywhere in the marker.
        assert str(tmp_path) not in raw
        assert ref["dir_hint"] == "../cluster"


def test_cluster_url_recorded_from_cluster_dir_origin(tmp_path):
    make_member(tmp_path, "alpha", [_node("app", source_file="src/app.ts")])
    cluster = tmp_path / "cluster"
    write_cluster(cluster, [{"tag": "alpha", "path": "../alpha"}])
    _fake_checkout(cluster, "https://github.com/org/my-cluster")
    build_cluster(cluster)
    ref = _only_ref(tmp_path / "alpha" / "graphify-out")
    assert ref["cluster_url"] == "https://github.com/org/my-cluster"


def test_cluster_url_empty_without_git(tmp_path, built_cluster):
    ref = _only_ref(tmp_path / "alpha" / "graphify-out")
    assert ref["cluster_url"] == ""


def test_skip_branch_backfills_missing_marker_only(tmp_path, built_cluster):
    alpha_marker = _marker(tmp_path, "alpha")
    beta_marker = _marker(tmp_path, "beta")
    alpha_marker.unlink()
    beta_before = beta_marker.read_bytes()
    beta_mtime = beta_marker.stat().st_mtime_ns

    summary = build_cluster(built_cluster)
    assert summary["skipped"]
    assert summary["refs_written"] == 1
    assert alpha_marker.is_file()
    assert beta_marker.read_bytes() == beta_before
    assert beta_marker.stat().st_mtime_ns == beta_mtime


def test_member_can_keep_multiple_cluster_memberships(tmp_path, built_cluster):
    make_member(tmp_path, "gamma", [_node("worker", source_file="src/worker.ts")])
    other = tmp_path / "other-cluster"
    write_cluster(other, [
        {"tag": "alpha", "path": "../alpha"},
        {"tag": "gamma", "path": "../gamma"},
    ], links=[{
        "type": "references",
        "from": {"repo": "alpha", "id": "app"},
        "to": {"repo": "gamma", "id": "worker"},
    }])
    spec_path = other / "cluster.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["name"] = "other-cluster"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    build_cluster(other)

    refs = load_cluster_refs(tmp_path / "alpha" / "graphify-out")
    assert [ref["cluster_name"] for ref in refs] == ["other-cluster", "test-cluster"]


def test_duplicate_cluster_name_across_remotes_is_rejected_before_writes(tmp_path):
    """Two clusters with the same name but DIFFERENT git remotes are a genuine
    collision: the build fails before any output is written, and keeps
    failing on retry (the check runs ahead of the unchanged-inputs skip)."""
    make_member(tmp_path, "alpha", [_node("app", source_file="src/app.ts")])
    first = tmp_path / "first"
    write_cluster(first, [{"tag": "alpha", "path": "../alpha"}])
    _fake_checkout(first, "https://github.com/org/first-cluster")
    build_cluster(first)

    duplicate = tmp_path / "duplicate"
    write_cluster(duplicate, [{"tag": "alpha", "path": "../alpha"}])
    _fake_checkout(duplicate, "https://github.com/org/other-cluster")

    for _attempt in range(2):  # sticky: the second run must not skip-and-pass
        with pytest.raises(ClusterSpecError, match="cluster names must be unique"):
            build_cluster(duplicate)
    assert not (duplicate / "graphify-out").exists()
    assert _only_ref(tmp_path / "alpha" / "graphify-out")["cluster_url"] == (
        "https://github.com/org/first-cluster"
    )


def test_moved_cluster_without_remote_rebuilds_and_refreshes_hint(tmp_path, capsys):
    """A dir_hint mismatch alone is not a name collision — a no-remote cluster
    that was moved (or laid out differently on another machine) must rebuild
    with a warning and refresh the marker, not hard-error."""
    import shutil

    make_member(tmp_path, "alpha", [_node("app", source_file="src/app.ts")])
    old_home = tmp_path / "clusters-old" / "demo"
    write_cluster(old_home, [{"tag": "alpha", "path": "../../alpha"}])
    build_cluster(old_home)
    assert _only_ref(tmp_path / "alpha" / "graphify-out")["dir_hint"].startswith(
        "../clusters-old"
    )

    new_home = tmp_path / "clusters-new" / "demo"
    new_home.parent.mkdir()
    shutil.move(str(old_home), str(new_home))  # same depth: the path hint still resolves

    summary = build_cluster(new_home, force=True)
    assert not summary["skipped"]
    assert "updating it" in capsys.readouterr().err
    assert _only_ref(tmp_path / "alpha" / "graphify-out")["dir_hint"].startswith(
        "../clusters-new"
    )


def test_named_cluster_selection_and_ambiguous_bare_flag(
    tmp_path, built_cluster, monkeypatch, capsys
):
    make_member(tmp_path, "gamma", [_node("worker", source_file="src/worker.ts")])
    other = tmp_path / "other-cluster"
    write_cluster(other, [
        {"tag": "alpha", "path": "../alpha"},
        {"tag": "gamma", "path": "../gamma"},
    ], links=[{
        "type": "references",
        "from": {"repo": "alpha", "id": "app"},
        "to": {"repo": "gamma", "id": "worker"},
    }])
    spec_path = other / "cluster.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["name"] = "other-cluster"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    build_cluster(other)

    monkeypatch.chdir(tmp_path / "alpha")
    code, out, err = _dispatch(
        ["explain", "worker", "--cluster", "other-cluster"], monkeypatch, capsys
    )
    assert code == 0 and "Node: worker" in out

    code, _out, err = _dispatch(["explain", "worker", "--cluster"], monkeypatch, capsys)
    assert code == 1
    assert "belongs to multiple clusters" in err
    assert "other-cluster" in err and "test-cluster" in err


def test_no_refs_opt_out(tmp_path):
    make_member(tmp_path, "alpha", [_node("app", source_file="src/app.ts")])
    cluster = tmp_path / "cluster"
    write_cluster(cluster, [{"tag": "alpha", "path": "../alpha"}])
    summary = build_cluster(cluster, write_refs=False)
    assert summary["refs_written"] == 0
    assert not _marker(tmp_path, "alpha").exists()


def test_cli_build_no_refs_and_remove_cleanup(tmp_path, capsys):
    make_member(tmp_path, "alpha", [_node("app", source_file="src/app.ts")])
    cluster = tmp_path / "cluster"
    write_cluster(cluster, [{"tag": "alpha", "path": "../alpha"}])

    code, out, _err = _run(["build", "--dir", str(cluster), "--no-refs"], capsys)
    assert code == 0
    assert not _marker(tmp_path, "alpha").exists()

    code, out, _err = _run(["build", "--dir", str(cluster), "--force"], capsys)
    assert code == 0 and "cluster-refs: wrote 1" in out
    assert _marker(tmp_path, "alpha").is_file()

    code, out, err = _run(["remove", "alpha", "--dir", str(cluster)], capsys)
    assert code == 0 and "also removed its cluster-ref.json" in out
    assert not _marker(tmp_path, "alpha").exists()


def test_cli_remove_unresolvable_member_soft_note(tmp_path, capsys):
    cluster = tmp_path / "cluster"
    write_cluster(cluster, [{"tag": "ghost", "url": "https://github.com/org/ghost"}])
    code, _out, err = _run(["remove", "ghost", "--dir", str(cluster)], capsys)
    assert code == 0
    assert "left in place" in err


# ---------------------------------------------------------------------------
# Reading + resolving markers
# ---------------------------------------------------------------------------

def test_load_cluster_refs_fail_soft(tmp_path):
    out = tmp_path / "graphify-out"
    out.mkdir()
    assert load_cluster_refs(out) == []  # missing
    marker = out / CLUSTER_REF_NAME
    marker.write_text("{not json", encoding="utf-8")
    assert load_cluster_refs(out) == []  # corrupt
    marker.write_text('["a list"]', encoding="utf-8")
    assert load_cluster_refs(out) == []  # non-dict
    marker.write_text('{"version": 1, "clusters": {}}', encoding="utf-8")
    assert load_cluster_refs(out) == []  # clusters is not a list
    marker.write_text(
        '{"version": 99, "clusters": []}', encoding="utf-8"
    )
    assert load_cluster_refs(out) == []  # unsupported version
    marker.write_text(
        '{"version": 1, "clusters": [{"cluster_name": "x", "self_tag": "a"}]}',
        encoding="utf-8",
    )
    assert load_cluster_refs(out)[0]["cluster_name"] == "x"
    marker.write_text(  # draft-era flat marker: clean break, regenerate via build
        '{"version": 1, "cluster_name": "x", "self_tag": "a"}', encoding="utf-8"
    )
    assert load_cluster_refs(out) == []


def test_resolve_cluster_dir_via_hint_then_discovery(tmp_path, built_cluster):
    ref = _only_ref(tmp_path / "alpha" / "graphify-out")
    assert resolve_cluster_dir(ref, tmp_path / "alpha") == tmp_path / "cluster"

    # Stale hint: move the cluster; discovery over parent siblings finds it.
    moved = tmp_path / "relocated-cluster"
    (tmp_path / "cluster").rename(moved)
    assert resolve_cluster_dir(ref, tmp_path / "alpha") == moved

    # Name mismatch is rejected everywhere.
    spec = json.loads((moved / "cluster.json").read_text(encoding="utf-8"))
    spec["name"] = "some-other-cluster"
    (moved / "cluster.json").write_text(json.dumps(spec), encoding="utf-8")
    assert resolve_cluster_dir(ref, tmp_path / "alpha") is None


def test_unresolvable_message_variants():
    with_url = {"cluster_name": "c", "self_tag": "a", "member_count": 3,
                "cluster_url": "https://github.com/org/c"}
    msg = unresolvable_message(with_url)
    assert "clone https://github.com/org/c" in msg and "member 'a'" in msg
    without = dict(with_url, cluster_url="")
    msg = unresolvable_message(without)
    assert "graphify cluster init" in msg and "no recorded remote" in msg


# ---------------------------------------------------------------------------
# --cluster flag + hints through the real CLI dispatch
# ---------------------------------------------------------------------------

def _dispatch(argv, monkeypatch, capsys):
    from graphify.cli import dispatch_command

    monkeypatch.setattr(sys, "argv", ["graphify"] + argv)
    code = 0
    try:
        dispatch_command(argv[0])
    except SystemExit as exc:
        code = exc.code or 0
    out, err = capsys.readouterr()
    return code, out, err


def test_cluster_flag_end_to_end(tmp_path, built_cluster, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path / "alpha")
    # Local graph has no 'server' node; the cluster graph does.
    code, out, err = _dispatch(["path", "app.ts", "server.ts", "--cluster"], monkeypatch, capsys)
    assert code == 0, err
    assert "calls_api" in out

    code, out, err = _dispatch(["explain", "server", "--cluster"], monkeypatch, capsys)
    assert code == 0
    assert "No node matching" not in out


def test_cluster_flag_mutually_exclusive_with_graph(tmp_path, built_cluster, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path / "alpha")
    code, _out, err = _dispatch(
        ["path", "a", "b", "--cluster", "--graph", "x.json"], monkeypatch, capsys
    )
    assert code == 1 and "mutually exclusive" in err


def test_cluster_flag_without_marker(tmp_path, monkeypatch, capsys):
    make_member(tmp_path, "solo", [_node("app", source_file="src/app.ts")])
    monkeypatch.chdir(tmp_path / "solo")
    code, _out, err = _dispatch(["explain", "app.ts", "--cluster"], monkeypatch, capsys)
    assert code == 1 and "not a known cluster member" in err


def test_cluster_flag_unresolvable_names_clone_url(tmp_path, built_cluster, monkeypatch, capsys):
    import shutil

    # Record a remote for the cluster, rebuild markers, then delete the cluster.
    _fake_checkout(built_cluster, "https://github.com/org/the-cluster")
    build_cluster(built_cluster, force=True)
    shutil.rmtree(built_cluster)
    monkeypatch.chdir(tmp_path / "alpha")
    code, _out, err = _dispatch(["explain", "server.ts", "--cluster"], monkeypatch, capsys)
    assert code == 1
    assert "clone https://github.com/org/the-cluster" in err


def test_cluster_found_but_unbuilt(tmp_path, built_cluster, monkeypatch, capsys):
    import shutil

    shutil.rmtree(built_cluster / "graphify-out")
    monkeypatch.chdir(tmp_path / "alpha")
    code, _out, err = _dispatch(["explain", "server.ts", "--cluster"], monkeypatch, capsys)
    assert code == 1 and "no built graph" in err


def test_hints_on_failures_with_marker(tmp_path, built_cluster, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path / "alpha")
    code, _out, err = _dispatch(["path", "app.ts", "no-such-thing"], monkeypatch, capsys)
    assert code == 1
    assert "member 'alpha' of cluster 'test-cluster'" in err

    code, out, _err = _dispatch(["explain", "no-such-thing"], monkeypatch, capsys)
    assert code == 0
    assert "member 'alpha' of cluster 'test-cluster'" in out

    code, out, _err = _dispatch(["affected", "no-such-thing"], monkeypatch, capsys)
    assert "member 'alpha' of cluster 'test-cluster'" in out


def test_no_hint_without_marker_or_on_explicit_graph(tmp_path, built_cluster, monkeypatch, capsys):
    make_member(tmp_path, "solo", [_node("app", source_file="src/app.ts")])
    monkeypatch.chdir(tmp_path / "solo")
    code, out, err = _dispatch(["explain", "no-such-thing"], monkeypatch, capsys)
    assert "cluster" not in out + err

    # Explicit --graph never hints, even when the CWD marker exists.
    monkeypatch.chdir(tmp_path / "alpha")
    other = tmp_path / "solo" / "graphify-out" / "graph.json"
    code, out, err = _dispatch(["explain", "no-such-thing", "--graph", str(other)], monkeypatch, capsys)
    assert "cluster" not in out + err


def test_corrupt_marker_never_hints_or_breaks(tmp_path, built_cluster, monkeypatch, capsys):
    _marker_path = tmp_path / "alpha" / "graphify-out" / CLUSTER_REF_NAME
    _marker_path.write_text("{corrupt", encoding="utf-8")
    monkeypatch.chdir(tmp_path / "alpha")
    code, out, err = _dispatch(["explain", "no-such-thing"], monkeypatch, capsys)
    assert code == 0
    assert "cluster" not in out + err


# ---------------------------------------------------------------------------
# Hook nudge
# ---------------------------------------------------------------------------

def _run_search_hook(monkeypatch, capsys):
    from graphify.cli import _run_hook_guard

    monkeypatch.setattr(
        sys, "stdin",
        type("S", (), {"buffer": __import__("io").BytesIO(
            json.dumps({"tool_input": {"command": "grep -r foo ."}}).encode()
        )})(),
    )
    _run_hook_guard("search", strict=False)
    out, _err = capsys.readouterr()
    return out


def test_hook_nudge_gains_cluster_line(tmp_path, built_cluster, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path / "alpha")
    out = _run_search_hook(monkeypatch, capsys)
    payload = json.loads(out)  # still valid JSON
    ctx = payload["hookSpecificOutput"]["additionalContext"]
    assert "member 'alpha' of cluster 'test-cluster'" in ctx


def test_hook_nudge_unchanged_without_marker(tmp_path, monkeypatch, capsys):
    from graphify.cli import _SEARCH_NUDGE

    make_member(tmp_path, "solo", [_node("app", source_file="src/app.ts")])
    monkeypatch.chdir(tmp_path / "solo")
    out = _run_search_hook(monkeypatch, capsys)
    assert out == _SEARCH_NUDGE  # byte-identical


# ---------------------------------------------------------------------------
# MCP serve
# ---------------------------------------------------------------------------

def test_serve_no_match_includes_cluster_note(tmp_path, built_cluster):
    mcp_types = pytest.importorskip("mcp").types
    import asyncio
    from graphify.serve import _build_server

    server = _build_server(str(tmp_path / "alpha" / "graphify-out" / "graph.json"))
    handler = server.request_handlers[mcp_types.CallToolRequest]
    req = mcp_types.CallToolRequest(
        method="tools/call",
        params=mcp_types.CallToolRequestParams(
            name="get_node", arguments={"label": "zz-no-such-node"}
        ),
    )
    text = asyncio.run(handler(req)).root.content[0].text
    assert "No node matching" in text
    assert "member 'alpha' of cluster 'test-cluster'" in text
